"""Диалоговый менеджер: приветствие → выбор направления кнопкой → ветка.

Принцип работы (по результатам первого тестирования):

**Приветствие → выбор направления кнопкой → диалог в выбранной ветке →
при необходимости оформление заявки.**

Категория клиента определяется ИСКЛЮЧИТЕЛЬНО нажатием одной из четырёх
кнопок главного меню. Свободный текст до выбора направления не
классифицируется — бот предлагает нажать кнопку. Внутри ветки бот отвечает
на вопросы по базе знаний (простой RAG: поиск фрагментов выбранной
категории + общие материалы → контекст модели Ollama).

Все зависимости (AI-клиент, поиск, база заявок) передаются извне — это
позволяет тестировать менеджер целиком без сети и без VK.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .ai_client import AIUnavailable, describe_ai_problem
from .booking.flow import BookingFlow, FlowAction
from .categorize import CATEGORY_LABELS, VALID_CATEGORIES
from . import keyboards
from .knowledge.loader import KnowledgeBase
from .knowledge.retriever import KeywordRetriever, RetrievalResult
from .prompts import load_prompt
from .storage import BookingDatabase

logger = logging.getLogger(__name__)

WELCOME = (
    "Здравствуйте! Я виртуальный помощник Smart Body Academy.\n\n"
    "Помогу вам разобраться с обучением Pilates, профессиональными "
    "программами и персональными тренировками.\n\n"
    "Выберите, пожалуйста, что вас интересует:"
)

CHOOSE_DIRECTION = (
    "Выберите, пожалуйста, одно из четырёх направлений кнопками ниже — "
    "после этого я отвечаю на вопросы по материалам Академии и помогаю "
    "оформить заявку."
)

MENU_PROMPT = "Выберите направление Академии:"

HELP = (
    "Я виртуальный помощник Smart Body Academy.\n\n"
    "Выберите направление кнопками в меню — и я отвечу на вопросы по "
    "материалам Академии (обучение, программы, тренировки) и помогу оформить "
    "предварительную заявку.\n\n"
    "Команды:\n"
    "/menu — выбрать направление из главного меню\n"
    "/book — оформить предварительную заявку (в выбранной ветке)\n"
    "/help — эта справка\n"
    "/cancel — отменить текущий сценарий\n\n"
    "Важно: через бота оформляются только предварительные заявки — "
    "представитель Академии связывается с вами и согласует все детали лично."
)

INSUFFICIENT_INFO = (
    "К сожалению, в материалах Академии по этому вопросу у меня нет "
    "подтверждённой информации, и я не хочу догадываться. Точные детали "
    "можно уточнить у представителя Академии: novikovsba@mail.ru или "
    "+7 (925) 964-77-72. Также я могу оформить предварительную заявку — "
    "командой /book."
)

SAVED = (
    "Ваша заявка №{id} отправлена представителю Академии. Это предварительное "
    "обращение: с вами свяжутся по контакту «{contact}» и согласуют детали "
    "лично. Спасибо!"
)

DB_ERROR = (
    "К сожалению, сейчас не удалось сохранить заявку — временная проблема "
    "с базой данных. Пожалуйста, попробуйте ещё раз чуть позже или напишите "
    "напрямую: novikovsba@mail.ru."
)

SWITCH_CONFIRM = (
    "Сейчас идёт заполнение заявки. Прервать заполнение (без сохранения "
    "черновика) и сменить направление? Напишите «да» или «нет»."
)

# Отдельной страницы записи на диагностику на сайте Академии нет
# (проверено по всем разделам smartbodyacademy.ru 2026-11-03): диагностика
# движения входит в первую тренировку (/training, /faq). Ссылку не
# придумываем — используем существующий сценарий заявки.
DIAGNOSTIC_FOOTER = (
    "Отдельная запись на диагностику не нужна — диагностика движения входит "
    "в первую тренировку. Чтобы прийти на первую тренировку, оформите "
    "предварительную заявку командой /book или кнопкой «Оставить заявку»: "
    "представитель Академии свяжется с вами и согласует формат и время."
)

CATEGORY_INTRO: dict[str, str] = {
    "specialist": (
        "Отлично! Я помогу с обучением на инструктора Pilates: программы, "
        "квалификация, форматы и условия обучения — по материалам Академии.\n\n"
        "Спрашивайте о программах и форматах — а предварительную заявку можно "
        "оставить командой /book или кнопкой ниже."
    ),
    "club": (
        "Понял вас! Расскажу о работе с фитнес-клубами и студиями: обучение "
        "команды на территории вашего клуба или студии (преподаватели "
        "Академии приезжают к вам), программы Matwork, внедрение направления "
        "пилатеса.\n\n"
        "Спрашивайте — а предварительную заявку от организации можно оставить "
        "командой /book или кнопкой ниже."
    ),
    "client": (
        "Прекрасно! Расскажу о персональных тренировках Pilates: форматы "
        "занятий, стоимость, условия и первая встреча-диагностика.\n\n"
        "Спрашивайте — а предварительную заявку на персональную тренировку "
        "можно оставить командой /book или кнопкой ниже."
    ),
}

# Международные семинары — индивидуальное согласование; обычный RAG-ответ
# в этом направлении не запускается: бот сразу честно говорит, что условия
# обсуждаются лично.
INTERNATIONAL_INFO = (
    "Международные семинары и мероприятия организуются по индивидуальному "
    "согласованию. Все условия сотрудничества, формат, программа, сроки и "
    "стоимость обсуждаются лично с Андреем Новиковым. Оставьте заявку, и мы "
    "свяжемся с вами для обсуждения деталей."
)


@dataclass
class Reply:
    """Сообщение, которое бот отправляет пользователю."""

    text: str
    keyboard: str | None = None


@dataclass
class UserState:
    """Состояние диалога с одним пользователем."""

    category: str | None = None  # выбранная кнопкой ветка
    greeted: bool = False  # приветствие уже показано
    flow: BookingFlow | None = None  # идёт заполнение заявки
    pending_switch: str | None = None  # подтверждение смены направления


class DialogueManager:
    """Обрабатывает сообщения: команды → выбор кнопкой → ветка → заявка."""

    def __init__(
        self,
        db: BookingDatabase,
        ai,  # OllamaClient
        kb: KnowledgeBase,
        system_prompt: str,
        retriever: KeywordRetriever | None = None,
    ) -> None:
        self.db = db
        self.ai = ai
        self.kb = kb
        self.retriever = retriever or KeywordRetriever(kb)
        self.system_prompt = system_prompt
        self.users: dict[int, UserState] = {}

    # ------------------------------------------------------------------ #
    #  Состояние                                                         #
    # ------------------------------------------------------------------ #

    def state(self, vk_id: int) -> UserState:
        return self.users.setdefault(vk_id, UserState())

    def reset(self, vk_id: int, *, keep_category: bool = False) -> UserState:
        """Сбросить ветку/сценарий. Вызывается вместе с показом меню или интро,
        поэтому ``greeted`` сохраняется — приветствие не повторяется."""

        st = self.state(vk_id)
        self.users[vk_id] = UserState(
            category=st.category if keep_category else None,
            greeted=True,
        )
        return self.users[vk_id]

    # ------------------------------------------------------------------ #
    #  Точка входа                                                       #
    # ------------------------------------------------------------------ #

    async def handle_message(
        self,
        vk_id: int,
        text: str,
        payload: dict | None = None,
    ) -> list[Reply]:
        """Обработать входящее сообщение и вернуть список ответов."""

        text = (text or "").strip()
        payload = payload or {}
        cmd = payload.get("cmd") or payload.get("/")
        category_choice = payload.get("category")

        # --- Команды и кнопки -------------------------------------------------
        command = cmd or text
        if command in ("/start", "start", "начать", "/menu", "меню"):
            return self._cmd_menu(vk_id)
        if command in ("/help", "help", "помощь"):
            return [Reply(HELP, keyboards.main_keyboard())]
        if command in ("/cancel", "отмена"):
            return self._cmd_cancel(vk_id)
        if command in ("/book", "book", "оставить заявку", "заявка"):
            return await self._cmd_book(vk_id)
        if cmd == "confirm_yes":
            return await self._cmd_confirm_yes(vk_id)
        if category_choice in VALID_CATEGORIES:
            return await self._cmd_pick_category(vk_id, category_choice)

        # --- Диалоги -----------------------------------------------------------
        state = self.state(vk_id)
        if state.pending_switch:
            return await self._handle_switch_answer(vk_id, text)
        if state.flow is not None:
            return await self._handle_flow(vk_id, text)
        if state.category is not None:
            return await self._handle_chat(vk_id, text)
        return self._handle_before_selection(vk_id, text)

    # ------------------------------------------------------------------ #
    #  Главное меню и выбор направления                                  #
    # ------------------------------------------------------------------ #

    def _cmd_menu(self, vk_id: int) -> list[Reply]:
        """Вернуться в главное меню.

        При первом обращении — полное приветствие с представлением; при
        каждом следующем вызове /start, /menu или кнопке возврата — только
        меню направлений, без повторения приветствия.
        """

        state = self.state(vk_id)
        if state.flow is not None:
            state.pending_switch = "menu"
            return [Reply(SWITCH_CONFIRM)]
        was_greeted = state.greeted
        self.reset(vk_id)
        text = WELCOME if not was_greeted else MENU_PROMPT
        return [Reply(text, keyboards.main_keyboard())]

    async def _cmd_pick_category(self, vk_id: int, category: str) -> list[Reply]:
        """Выбор направления кнопкой — единственный способ задать категорию."""

        state = self.state(vk_id)
        if state.flow is not None:
            # заполнение заявки идёт: не выбрасываем черновик без спроса
            state.pending_switch = category
            return [Reply(SWITCH_CONFIRM)]

        state = self.reset(vk_id)  # reset заменяет объект состояния
        state.category = category
        if category == "international":
            # информационное сообщение вместо интро и RAG
            return [Reply(INTERNATIONAL_INFO,
                          keyboards.category_keyboard(category))]
        return [Reply(
            CATEGORY_INTRO[category],
            keyboards.category_keyboard(category),
        )]

    async def _handle_switch_answer(self, vk_id: int, text: str) -> list[Reply]:
        """Ответ на вопрос «прервать заполнение заявки?»."""

        state = self.state(vk_id)
        target = state.pending_switch
        lowered = text.lower()
        if lowered in {"да", "давай", "ок", "окей", "yes"}:
            state.pending_switch = None
            state.flow = None
            if target == "menu":
                self.reset(vk_id)
                return [Reply(MENU_PROMPT, keyboards.main_keyboard())]
            return await self._cmd_pick_category(vk_id, target)
        if lowered in {"нет", "не нужно", "отмена", "no"}:
            state.pending_switch = None
            flow = state.flow
            question = flow.current_question() if flow else MENU_PROMPT
            return [Reply(
                "Хорошо, продолжаем заполнение заявки.\n\n" + question,
            )]
        return [Reply(SWITCH_CONFIRM)]

    # ------------------------------------------------------------------ #
    #  До выбора направления: никаких ответов и классификации            #
    # ------------------------------------------------------------------ #

    def _handle_before_selection(self, vk_id: int, text: str) -> list[Reply]:
        """Свободный текст до выбора направления.

        Бот не угадывает намерения: показывает приветствие один раз, дальше
        предлагает нажать кнопку направления.
        """

        state = self.state(vk_id)
        if not state.greeted:
            state.greeted = True
            return [Reply(WELCOME, keyboards.main_keyboard())]
        return [Reply(CHOOSE_DIRECTION, keyboards.main_keyboard())]

    # ------------------------------------------------------------------ #
    #  Команды                                                           #
    # ------------------------------------------------------------------ #

    def _cmd_cancel(self, vk_id: int) -> list[Reply]:
        state = self.state(vk_id)
        if state.flow is not None:
            self.reset(vk_id, keep_category=True)
            return [
                Reply(
                    "Окей, отменяю заполнение заявки. Черновик не сохранён.",
                    keyboards.category_keyboard(self.state(vk_id).category or "client"),
                )
            ]
        return [
            Reply(
                "Здесь нечего отменять — активных сценариев нет. Выберите "
                "направление в меню и продолжим.",
                keyboards.main_keyboard(),
            )
        ]

    async def _cmd_book(self, vk_id: int) -> list[Reply]:
        """Заявка доступна только после выбора направления (кнопкой)."""

        state = self.state(vk_id)
        if state.flow is not None:
            return [Reply("Сценарий заявки уже идёт. Продолжим:"),
                    Reply(state.flow.current_question())]
        if state.category is None:
            return [Reply(
                "Чтобы заявка попала в нужный раздел, сначала выберите "
                "направление кнопкой:",
                keyboards.main_keyboard(),
            )]
        state.flow = BookingFlow(state.category)
        return [Reply(
            state.flow.prompt_with_intro(),
            keyboards.category_keyboard(state.category),
        )]

    async def _cmd_confirm_yes(self, vk_id: int) -> list[Reply]:
        state = self.state(vk_id)
        if state.flow is None:
            return [Reply("Активной заявки сейчас нет. Начать заново можно "
                          "командой /book в выбранном направлении.")]
        return await self._submit_booking(vk_id)

    # ------------------------------------------------------------------ #
    #  Свободное общение в выбранной ветке (RAG)                         #
    # ------------------------------------------------------------------ #

    async def _handle_chat(self, vk_id: int, text: str) -> list[Reply]:
        state = self.state(vk_id)
        if not text:
            return [Reply(
                "Напишите вопрос по выбранному направлению или /menu — "
                "сменить направление.",
                keyboards.category_keyboard(state.category),
            )]
        if state.category == "international":
            # международных семинаров RAG не запускается: только индивидуальное согласование
            return [Reply(INTERNATIONAL_INFO,
                          keyboards.category_keyboard("international"))]
        reply_text = await self._rag_answer(text, state.category or "client")
        return [Reply(reply_text, keyboards.category_keyboard(state.category))]

    # ------------------------------------------------------------------ #
    #  Сценарий заявки                                                   #
    # ------------------------------------------------------------------ #

    async def _handle_flow(self, vk_id: int, text: str) -> list[Reply]:
        state = self.state(vk_id)
        flow = state.flow
        if flow is None:  # безопасность
            return [Reply(HELP)]

        result = flow.handle(text)
        if result.action == FlowAction.ASK:
            kb = keyboards.confirm_keyboard() if flow.step.value == "confirm" else None
            return [Reply(result.answer or flow.current_question(), kb)]
        if result.action == FlowAction.CONFIRM:
            return [Reply(flow.data.summary(), keyboards.confirm_keyboard())]
        if result.action == FlowAction.SUBMIT:
            return await self._submit_booking(vk_id)
        if result.action == FlowAction.CANCELLED:
            answer = result.answer
            self.reset(vk_id, keep_category=True)
            return [Reply(answer, keyboards.category_keyboard(
                self.state(vk_id).category or "client"))]
        # ANSWERED: попутный вопрос — отвечаем по базе знаний (или фиксированным
        # сообщением для международных семинаров) и продолжаем сценарий
        if state.category == "international":
            rag = INTERNATIONAL_INFO
        else:
            rag = await self._rag_answer(text, state.category or "client")
        answer_flow = flow.resume_after_answer()
        return [Reply(rag), Reply(answer_flow.answer)]

    async def _submit_booking(self, vk_id: int) -> list[Reply]:
        state = self.state(vk_id)
        flow = state.flow
        if flow is None:
            return [Reply("Активной заявки сейчас нет.")]
        data = flow.data
        try:
            record = self.db.save_booking(
                vk_id=vk_id,
                category=data.category,
                name=data.name,
                contact=data.contact,
                request_text=data.request_text,
                details=dict(data.details),
            )
        except Exception:  # noqa: BLE001 — база не должна ронять бота
            logger.exception("Не удалось сохранить заявку в SQLite")
            return [Reply(DB_ERROR)]
        logger.info(
            "[DB] заявка №%s сохранена: категория=%s, имя=%s, контактов=%d",
            record.id, record.category, record.name, len(record.details) + 2,
        )
        self.reset(vk_id, keep_category=True)
        return [
            Reply(
                SAVED.format(id=record.id, contact=record.contact),
                keyboards.category_keyboard(self.state(vk_id).category or "client"),
            )
        ]

    # ------------------------------------------------------------------ #
    #  RAG                                                               #
    # ------------------------------------------------------------------ #

    async def _rag_answer(self, text: str, category: str) -> str:
        """Ответ по фрагментам базы знаний выбранной категории (+ общие)."""

        retrieval_started = time.perf_counter()
        result: RetrievalResult = self.retriever.search(text, category)
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        logger.info(
            "[RAG] поиск: %.1f мс | фрагментов: %d | контекст: %d символов | категория: %s",
            retrieval_ms, len(result.fragments), len(result.context_text), category,
        )
        if not result.fragments:
            return INSUFFICIENT_INFO
        answer = await self.ai.ask(
            text,
            system_prompt=self.system_prompt,
            context=result.context_text,
        )
        if isinstance(answer, AIUnavailable):
            logger.warning("AI недоступен: %s (%s)", answer.reason.value, answer.detail[:120])
            return describe_ai_problem(answer)
        return self._with_action_hints(category, answer.text, result.context_text)

    # ------------------------------------------------------------------ #
    #  Приписки по действию пользователя                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _with_action_hints(category: str, answer: str, context: str) -> str:
        """Добавить к ответу подсказку, если он коснулся диагностики.

        По собранным материалам Академии отдельной страницы записи на
        диагностику на сайте нет: диагностика движения входит в первую
        тренировку (страницы /training и /faq). Поэтому ссылку не
        придумываем — вместо неё объясняем, как оформить заявку на первую
        тренировку. Подсказка добавляется только для ветки частных клиентов
        и только когда диагностика действительно затронута в ответе модели.
        """

        if category != "client":
            return answer
        if "диагностик" not in answer.lower():
            return answer
        return f"{answer}\n\n{DIAGNOSTIC_FOOTER}"


__all__ = ["DialogueManager", "HELP", "Reply", "UserState"]