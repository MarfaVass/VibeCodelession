"""Диалоговый менеджер: маршрутизация сообщений и сценарии.

Связывает компоненты вместе и хранит состояние диалогов пользователей:

* ``chat`` — свободное общение внутри выбранного направления (RAG);
* ``awaiting_category`` — бот ждёт, пока клиент определится с направлением
  (в т.ч. после уточняющего вопроса);
* ``booking`` — идёт пошаговый сценарий предварительной заявки.

Все зависимости (AI-клиент, поиск, база заявок) передаются извне — это
позволяет тестировать менеджер целиком без сети и без VK.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .ai_client import AIUnavailable, describe_ai_problem
from .booking.flow import BookingFlow, FlowAction
from .categorize import (
    CATEGORY_LABELS,
    CLARIFYING_QUESTION,
    CategoryDecision,
    VALID_CATEGORIES,
    classify_client,
)
from . import keyboards
from .knowledge.loader import KnowledgeBase
from .knowledge.retriever import KeywordRetriever, RetrievalResult
from .prompts import load_prompt
from .storage import BookingDatabase

logger = logging.getLogger(__name__)

WELCOME = (
    "Здравствуйте! Добро пожаловать в Smart Body Academy — Академию умного "
    "тела Андрея Новикова.\n\n"
    "Подскажите, пожалуйста, что вас интересует? Выберите направление кнопкой "
    "или напишите своими словами — я определю, чем помочь."
)

HELP = (
    "Я виртуальный администратор Smart Body Academy. Помогу разобраться в "
    "направлениях Академии и оформить предварительную заявку.\n\n"
    "Команды:\n"
    "/menu — выбрать направление из главного меню\n"
    "/book — оформить предварительную заявку\n"
    "/help — эта справка\n"
    "/cancel — отменить текущий сценарий\n\n"
    "Вы можете просто писать вопросы своими словами — для каждого направления "
    "я отвечаю по материалам Академии: обучение тренеров, работа с клубами, "
    "международные семинары, персональные тренировки.\n\n"
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

CANNOT_CLASSIFY = (
    "Не смог точно определить, какое направление вам подходит. "
    "Выберите, пожалуйста, кнопкой или уточните своими словами."
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

CATEGORY_INTRO: dict[str, str] = {
    "specialist": (
        "Отлично! Посмотрю на вас глазами частного специалиста: обучение "
        "пилатес-методике, повышение квалификации и сертификация. "
        "Программы ведёт лично Андрей Новиков.\n\n"
        "Спрашивайте о программах, форматах и условиях — а заявка оформляется "
        "командой /book или кнопкой ниже."
    ),
    "club": (
        "Понял вас! Расскажу о работе с фитнес-клубами и студиями: обучение "
        "команды на территории клуба, программы Matwork, внедрение "
        "направления пилатеса.\n\n"
        "Спрашивайте — а заявку на сотрудничество можно оставить командой "
        "/book или кнопкой ниже."
    ),
    "international": (
        "Great! I can help you as an international partner: inviting Andrey "
        "Novikov for seminars, masterclasses and multi-module trainings at "
        "your academy or conference.\n\n"
        "Ask me anything about the programs — or leave a request with /book. "
        "(Я также могу продолжить на русском.)"
    ),
    "client": (
        "Прекрасно! Расскажу о персональных тренировках: форматы занятий, "
        "стоимость, условия и первая встреча-диагностика.\n\n"
        "Спрашивайте — а предварительную заявку можно оставить командой /book "
        "или кнопкой ниже."
    ),
}


@dataclass
class Reply:
    """Сообщение, которое бот отправляет пользователю."""

    text: str
    keyboard: str | None = None


@dataclass
class UserState:
    """Состояние диалога с одним пользователем."""

    category: str | None = None
    awaiting_category: bool = False
    wanted_booking: bool = False
    flow: BookingFlow | None = None


class DialogueManager:
    """Обрабатывает сообщения: команды → меню → категории → сценарии."""

    def __init__(
        self,
        db: BookingDatabase,
        ai,  # OllamaClient
        kb: KnowledgeBase,
        system_prompt: str,
        classify_prompt: str,
        retriever: KeywordRetriever | None = None,
    ) -> None:
        self.db = db
        self.ai = ai
        self.kb = kb
        self.retriever = retriever or KeywordRetriever(kb)
        self.system_prompt = system_prompt
        self.classify_prompt = classify_prompt
        self.users: dict[int, UserState] = {}

    # ------------------------------------------------------------------ #
    #  Состояние                                                         #
    # ------------------------------------------------------------------ #

    def state(self, vk_id: int) -> UserState:
        return self.users.setdefault(vk_id, UserState())

    def reset(self, vk_id: int, *, keep_category: bool = False) -> UserState:
        st_category = self.state(vk_id).category if keep_category else None
        self.users[vk_id] = UserState(category=st_category)
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
        if command in ("/start", "start", "начать"):
            return await self._cmd_start(vk_id)
        if command in ("/help", "help", "помощь"):
            return [Reply(HELP, keyboards.main_keyboard())]
        if command in ("/menu", "меню"):
            return await self._cmd_menu(vk_id)
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
        if state.flow is not None:
            return await self._handle_flow(vk_id, text)
        if state.category is not None:
            return await self._handle_chat(vk_id, text)
        return await self._handle_new_user(vk_id, text)

    # ------------------------------------------------------------------ #
    #  Команды                                                           #
    # ------------------------------------------------------------------ #

    async def _cmd_start(self, vk_id: int) -> list[Reply]:
        state = self.reset(vk_id)
        state.awaiting_category = True
        return [
            Reply(WELCOME, keyboards.main_keyboard()),
        ]

    async def _cmd_menu(self, vk_id: int) -> list[Reply]:
        state = self.reset(vk_id)
        state.awaiting_category = True
        return [
            Reply(
                "Выберите направление Академии, о котором хотите узнать:\n\n"
                + "\n".join(f"• {name}" for name in CATEGORY_LABELS.values()),
                keyboards.main_keyboard(),
            )
        ]

    def _cmd_cancel(self, vk_id: int) -> list[Reply]:
        state = self.state(vk_id)
        if state.flow is not None:
            self.reset(vk_id, keep_category=True)
            return [
                Reply(
                    "Окей, отменяю заполнение заявки. Могу ответить на вопросы "
                    "или начать заново командой /book.",
                    keyboards.category_keyboard(self.state(vk_id).category or "client"),
                )
            ]
        return [
            Reply(
                "Здесь нечего отменять — активных сценариев нет. Напишите вопрос "
                "или выберите направление в меню.",
                keyboards.main_keyboard(),
            )
        ]

    async def _cmd_book(self, vk_id: int) -> list[Reply]:
        state = self.state(vk_id)
        if state.flow is not None:
            return [Reply("Сценарий заявки уже идёт. Продолжим:")] + [
                Reply(state.flow.current_question())
            ]
        if state.category is None:
            state.wanted_booking = True
            state.awaiting_category = True
            return [
                Reply(
                    "Чтобы заявка попала к нужному специалисту, уточним "
                    "направление Академии:",
                    keyboards.main_keyboard(),
                )
            ]
        state.flow = BookingFlow(state.category)
        return [Reply(
            state.flow.prompt_with_intro(),
            keyboards.category_keyboard(state.category),
        )]

    async def _cmd_confirm_yes(self, vk_id: int) -> list[Reply]:
        state = self.state(vk_id)
        if state.flow is None:
            return [Reply("Активной заявки сейчас нет. Начать заново можно командой /book.")]
        return await self._submit_booking(vk_id)

    async def _cmd_pick_category(self, vk_id: int, category: str) -> list[Reply]:
        state = self.reset(vk_id, keep_category=False)
        state.category = category
        intro = CATEGORY_INTRO[category]
        wanted_booking, state.wanted_booking = state.wanted_booking, False
        replies = [Reply(intro, keyboards.category_keyboard(category))]
        if wanted_booking:
            state.flow = BookingFlow(category)
            replies.append(Reply(state.flow.prompt_with_intro()))
        return replies

    # ------------------------------------------------------------------ #
    #  Новые пользователи и классификация                                #
    # ------------------------------------------------------------------ #

    async def _handle_new_user(self, vk_id: int, text: str) -> list[Reply]:
        if not text:
            return [Reply(WELCOME, keyboards.main_keyboard())]
        state = self.state(vk_id)
        state.awaiting_category = True
        replies: list[Reply] = [Reply(WELCOME)]
        decision = await self._decide_category(vk_id, text)
        if decision.is_confident:
            state.category = decision.category
            state.awaiting_category = False
            replies.append(Reply(CATEGORY_INTRO[decision.category],
                                 keyboards.category_keyboard(decision.category)))
            if text and not text.startswith("/"):
                rag = await self._rag_answer(text, decision.category)
                replies.append(Reply(rag))
            return replies
        return replies + [Reply(CLARIFYING_QUESTION, keyboards.main_keyboard())]

    async def _decide_category(self, vk_id: int, text: str) -> CategoryDecision:
        return await classify_client(text, self.ai, self.classify_prompt)

    # ------------------------------------------------------------------ #
    #  Свободное общение в выбранной категории                           #
    # ------------------------------------------------------------------ #

    async def _handle_chat(self, vk_id: int, text: str) -> list[Reply]:
        state = self.state(vk_id)
        lowered = text.lower()
        if lowered in {"меню", "другое направление"}:
            return await self._cmd_menu(vk_id)
        if not text:
            return [Reply(
                "Напишите вопрос по выбранному направлению или /menu — "
                "сменить направление.",
                keyboards.category_keyboard(state.category),
            )]
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
        # ANSWERED: попутный вопрос — идём в RAG, потом продолжаем сценарий
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
        """Ответ по фрагментам базы знаний выбранной категории."""

        result: RetrievalResult = self.retriever.search(text, category)
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
        return answer.text


__all__ = ["DialogueManager", "HELP", "Reply", "UserState"]