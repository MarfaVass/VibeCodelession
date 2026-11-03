"""Пошаговые сценарии сбора предварительных заявок.

Единый конечный автомат :class:`BookingFlow`, настраиваемый списком шагов —
поэтому четыре сценария (специалист, клуб, международная организация,
частный клиент) работают на одной проверенной логике.

Обязательный минимум — только имя и контакт; остальные поля необязательные.
Необязательный шаг клиент может пропустить словом «пропустить».

Во время сценария клиент может задать вопрос — тогда вопрос уходит в
AI-консультанта (RAG по соответствующему разделу базы знаний), а диалог
продолжается с того же шага.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable

from ..categorize import CATEGORY_LABELS

SKIP_WORDS = frozenset({"пропустить", "-", "--", "нет", "не нужно", "skip"})


class FlowStep(StrEnum):
    """Шаг сценария."""

    NAME = "name"
    CONTACT = "contact"
    REQUEST = "request"
    FIELD = "field"  # категорииные дополнительные поля
    CONFIRM = "confirm"
    DONE = "done"


class FlowAction(StrEnum):
    """Что диалоговому менеджеру делать с результатом шага."""

    ASK = "ask"  # задать (повторно) текущий вопрос
    CONFIRM = "confirm"  # показать сводку и запросить подтверждение
    SUBMIT = "submit"  # клиент подтвердил — сохранять заявку
    CANCELLED = "cancelled"  # клиент отменил сценарий
    ANSWERED = "answered"  # попутно обработан вопрос/AI-ответ


@dataclass(frozen=True)
class FieldSpec:
    """Описание одного категорииного поля."""

    key: str
    question: str
    required: bool = False


@dataclass
class BookingData:
    """Собранные данные заявки."""

    category: str
    name: str = ""
    contact: str = ""
    request_text: str = ""
    details: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        """Человекочитаемая сводка для подтверждения."""

        label = CATEGORY_LABELS.get(self.category, self.category)
        lines = [
            "Проверьте, пожалуйста, данные заявки:",
            "",
            f"📌 Направление: {label}",
            f"👤 Имя: {self.name}",
            f"📞 Контакт: {self.contact}",
        ]
        if self.request_text:
            lines.append(f"📝 Запрос: {self.request_text}")
        for key, value in self.details.items():
            lines.append(f"• {key}: {value}")
        lines.extend(
            [
                "",
                "Это предварительная заявка: представитель Академии свяжется с вами "
                "и согласует все детали лично.",
                "Отправить заявку?",
            ]
        )
        return "\n".join(lines)


@dataclass
class FlowResult:
    """Итог обработки очередного сообщения клиента."""

    action: FlowAction
    answer: str = ""  # текст для отправки клиенту
    step: FlowStep = FlowStep.NAME

    @property
    def is_terminal(self) -> bool:
        return self.action in (FlowAction.SUBMIT, FlowAction.CANCELLED)


# --------------------------------------------------------------------- #
#  Спецификации сценариев                                                #
# --------------------------------------------------------------------- #

_INTRO = (
    "Заполним короткую предварительную заявку — представитель Академии "
    "свяжется с вами и согласует все детали.\n"
    "В любой момент можно отменить командой /cancel "
    "и задать любой вопрос о занятиях — я на него отвечу и продолжим."
)

FIELD_SPECS: dict[str, tuple[FieldSpec, ...]] = {
    "specialist": (
        FieldSpec(
            key="интересующее направление",
            question=(
                "Какое направление обучения вас интересует? "
                "(Matwork 1, Matwork 2, работа на большом оборудовании — "
                "или напишите «помогите выбрать»)"
            ),
        ),
        FieldSpec(
            key="текущий опыт",
            question=(
                "Расскажите немного о вашем опыте. "
                "Например: «тренер общего профиля», «инструктор пилатеса», "
                "«без опыта». Можно пропустить."
            ),
        ),
        FieldSpec(
            key="формат обучения",
            question=(
                "Какой формат удобен: очное обучение в мини-группе в студии "
                "Академии в Москве, или другой вариант? Поле можно пропустить."
            ),
        ),
    ),
    "club": (
        FieldSpec(
            key="организация",
            question="Как называется ваш фитнес-клуб или студия (и город)?",
            required=True,
        ),
        FieldSpec(
            key="контактное лицо",
            question="Кто будет контактным лицом? Можно вписать своё имя.",
        ),
        FieldSpec(
            key="сотрудников",
            question=(
                "Сколько сотрудников планируется обучить? "
                "Ориентировочно — можно пропустить."
            ),
        ),
        FieldSpec(
            key="интересующая программа",
            question=(
                "Какая программа интересна: Matwork 1, Matwork 2, большое "
                "оборудование или комплексное обучение?"
            ),
        ),
        FieldSpec(
            key="пожелания",
            question="Есть ли дополнительные пожелания к семинару? Можно пропустить.",
        ),
    ),
    "international": (
        FieldSpec(
            key="страна",
            question="Which country are you writing from?",
        ),
        FieldSpec(
            key="организация",
            question=(
                "Is there an organization or studio behind the request? "
                "Private person is fine — you can skip this."
            ),
        ),
        FieldSpec(
            key="формат мероприятия",
            question=(
                "What event format interests you: a seminar, a masterclass "
                "or a multi-module training?"
            ),
        ),
        FieldSpec(
            key="тема или пожелания",
            question=(
                "What topic or notes should we pass to Andrey? (you can skip)"
            ),
        ),
        FieldSpec(
            key="предполагаемые сроки",
            question=(
                "Are there preferred dates or a time frame? (you can skip)"
            ),
        ),
    ),
    "client": (
        FieldSpec(
            key="формат тренировок",
            question=(
                "Какой формат вам интересен: тренировки в студии Академии, "
                "выезд на вашу территорию или онлайн?"
            ),
        ),
        FieldSpec(
            key="способ занятий",
            question=(
                "Предпочитаете разовое занятие или курс? Интересует пробное "
                "занятие? Пишите свободно."
            ),
        ),
        FieldSpec(
            key="пожелания",
            question="Есть особые пожелания или ограничения по здоровью, о которых стоит знать? Можно пропустить.",
        ),
    ),
}


class BookingFlow:
    """Конечный автомат сценария заявки для одной категории."""

    def __init__(self, category: str) -> None:
        if category not in FIELD_SPECS:
            raise ValueError(f"Нет сценария заявки для категории {category}")
        self.category = category
        self.data = BookingData(category=category)
        self.step: FlowStep = FlowStep.NAME
        self._field_index = 0

    # ------------------------------------------------------------------ #
    #  Вспомогательное                                                   #
    # ------------------------------------------------------------------ #

    def _current_field(self) -> FieldSpec | None:
        fields = FIELD_SPECS[self.category]
        if self._field_index < len(fields):
            return fields[self._field_index]
        return None

    def _next_step(self) -> FlowStep:
        if self._current_field() is not None:
            return FlowStep.FIELD
        return FlowStep.CONFIRM

    @staticmethod
    def _clean(text: str) -> str:
        return (text or "").strip()

    # ------------------------------------------------------------------ #
    #  Основной обработчик                                               #
    # ------------------------------------------------------------------ #

    def handle(self, text: str) -> FlowResult:
        """Обработать сообщение клиента на текущем шаге сценария.

        Вопросы (текст со знаком «?» или начинающийся с вопросительного
        слова) возвращаются менеджеру через ``FlowAction.ANSWERED``
        с пометкой — менеджер пойдёт в AI и потом вызовет
        :meth:`resume_after_answer`.
        """

        raw = self._clean(text)
        lowered = raw.lower()

        if lowered in {"отмена", "/cancel", "cancel", "стоп"}:
            return FlowResult(
                action=FlowAction.CANCELLED,
                answer="Окей, отменяю заполнение заявки. Я рядом, если что-то понадобится.",
                step=self.step,
            )

        if self._is_question(raw):
            return FlowResult(action=FlowAction.ANSWERED, step=self.step)

        if self.step == FlowStep.NAME:
            return self._handle_name(raw)
        if self.step == FlowStep.CONTACT:
            return self._handle_contact(raw)
        if self.step == FlowStep.REQUEST:
            return self._handle_request(lowered)
        if self.step == FlowStep.FIELD:
            return self._handle_field(raw, lowered)
        if self.step == FlowStep.CONFIRM:
            return self._handle_confirm(lowered)
        return FlowResult(action=FlowAction.ASK, answer="", step=self.step)

    def resume_after_answer(self) -> FlowResult:
        """Повторить вопрос текущего шага после AI-ответа на попутный вопрос.

        На шаге подтверждения снова показывается сводка с клавиатурой
        подтверждения, на остальных шагах — вопрос этого шага.
        """

        return self._step_transition_result() if self.step == FlowStep.CONFIRM \
            else FlowResult(action=FlowAction.ASK, answer=self.current_question(), step=self.step)

    def current_question(self) -> str:
        """Вопрос, который задан на текущем шаге."""

        if self.step == FlowStep.NAME:
            return "Как вас зовут? (пожалуйста, укажите имя и фамилию)"
        if self.step == FlowStep.CONTACT:
            return (
                "Оставьте контакт для связи: телефон, ссылку на профиль "
                "или почту — что вам удобно."
            )
        if self.step == FlowStep.REQUEST:
            return (
                "Пара слов о вашем запросе (необязательно): что хотите обсудить "
                "с представителем Академии? Можно пропустить."
            )
        if self.step == FlowStep.FIELD:
            spec = self._current_field()
            return spec.question if spec else ""
        if self.step == FlowStep.CONFIRM:
            return "Отправить заявку? Напишите «да» или «нет»."
        return ""

    def prompt_with_intro(self) -> str:
        """Первое сообщение сценария: вступление + вопрос имени."""

        return f"{_INTRO}\n\n{self.current_question()}"

    # ------------------------------------------------------------------ #
    #  Шаги                                                              #
    # ------------------------------------------------------------------ #

    def _handle_name(self, raw: str) -> FlowResult:
        value = raw.lstrip("!.")
        words = value.split()
        # «да/нет/ок» — это ответы на подтверждения, а не имя
        if low := value.lower().strip():
            if low in {"да", "нет", "ок", "окей", "yes", "no"}:
                if self.step == FlowStep.NAME:
                    return FlowResult(
                        action=FlowAction.ASK,
                        answer="Это похоже на ответ «да/нет» — напишите, пожалуйста, "
                               "имя и фамилию для заявки.",
                        step=FlowStep.NAME,
                    )
        if len(value) < 2 or len(words) > 4 or not any(ch.isalpha() for ch in value):
            return FlowResult(
                action=FlowAction.ASK,
                answer="Похоже, имя указано не полностью. Напишите, пожалуйста, имя и фамилию.",
                step=FlowStep.NAME,
            )
        self.data.name = value[:80]
        self.step = FlowStep.CONTACT
        return FlowResult(action=FlowAction.ASK, answer=self.current_question(), step=self.step)

    def _handle_contact(self, raw: str) -> FlowResult:
        digits = sum(ch.isdigit() for ch in raw)
        if len(raw) < 4 or (digits == 0 and "@" not in raw and "http" not in raw
                             and not re_link(raw)):
            return FlowResult(
                action=FlowAction.ASK,
                answer=(
                    "Не похоже на контакт. Укажите телефон, почту или ссылку "
                    "на профиль — чтобы представитель Академии мог с вами связаться."
                ),
                step=FlowStep.CONTACT,
            )
        self.data.contact = raw[:120]
        self.step = FlowStep.REQUEST
        return FlowResult(action=FlowAction.ASK, answer=self.current_question(), step=self.step)

    def _handle_request(self, lowered: str) -> FlowResult:
        if lowered in SKIP_WORDS or lowered in {"skip", "не нужно"}:
            self.data.request_text = ""
        else:
            self.data.request_text = self._clean(lowered)[:600]
        self.step = self._next_step()
        return self._step_transition_result()

    def _handle_field(self, raw: str, lowered: str) -> FlowResult:
        spec = self._current_field()
        assert spec is not None
        if lowered in SKIP_WORDS or lowered in {"skip", "не нужно", "не важно"}:
            value = ""
        else:
            value = raw[:200]
        if spec.required and not value:
            # обязательные категории поля нельзя пропустить
            return FlowResult(
                action=FlowAction.ASK,
                answer=f"Обязательно нужно указать: {spec.question}",
                step=FlowStep.FIELD,
            )
        if value:
            self.data.details[spec.key] = value
        self._field_index += 1
        self.step = self._next_step()
        return self._step_transition_result()

    def _step_transition_result(self) -> FlowResult:
        """Результат перехода на следующий шаг сценария.

        При переходе на шаг подтверждения возвращается сводка собранных
        данных (``FlowAction.CONFIRM``) — менеджер прикрепит к ней
        inline-клавиатуру подтверждения. Иначе — вопрос следующего шага.
        """

        if self.step == FlowStep.CONFIRM:
            return FlowResult(
                action=FlowAction.CONFIRM,
                answer=self.data.summary(),
                step=self.step,
            )
        return FlowResult(action=FlowAction.ASK, answer=self.current_question(), step=self.step)

    def _handle_confirm(self, lowered: str) -> FlowResult:
        if lowered.startswith("да") or lowered in {"ок", "окей", "подтверждаю", "yes", "отправить"}:
            return FlowResult(action=FlowAction.SUBMIT, step=FlowStep.DONE)
        if lowered.startswith("нет") or lowered in {"отмена", "не нужно", "отменить"}:
            return FlowResult(
                action=FlowAction.CANCELLED,
                answer="Заявка не отправлена. Могу заполнить заново командой /book.",
                step=FlowStep.DONE,
            )
        extra = self._is_question(lowered)
        if extra:
            return FlowResult(action=FlowAction.ANSWERED, step=FlowStep.CONFIRM)
        return FlowResult(
            action=FlowAction.ASK,
            answer="Напишите «да» — отправим заявку, или «нет» — отменим её.",
            step=FlowStep.CONFIRM,
        )

    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_question(text: str) -> bool:
        """Похоже ли сообщение на попутный вопрос, а не на ответ."""

        lowered = text.lower().strip()
        if lowered.endswith("?"):
            return True
        starters = (
            "а если", "а можно", "вопрос", "подскажите", "сколько",
            "почему", "зачем", "когда", "где", "можно ли", "что если",
            "what", "when", "where", "how", "why", "is there", "can i",
        )
        return lowered.startswith(starters)


def re_link(text: str) -> bool:
    """Простая проверка «похоже на ссылку/юзернейм»."""

    import re

    return bool(re.search(r"(vk\.me|vk\.com|https?://|t\.me|@[A-Za-z0-9_])", text, re.I))


def new_booking_flow(category: str) -> BookingFlow:
    """Фабрика сценариев заявок."""

    return BookingFlow(category)