"""Определение категории клиента.

Два уровня:

1. Детерминированный поиск по ключевым словам (быстро, бесплатно,
   полностью проверяется тестами).
2. AI-фолбэк через Ollama с жёстким промптом-классификатором, если по
   ключевым словам категория не определилась.

Результат — либо уверенная категория, либо :attr:`CategoryStatus.AMBIGUOUS`,
после которого диалоговый менеджер задаёт один уточняющий вопрос.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .ai_client import AIAnswer, AIFailureReason, AIUnavailable, OllamaClient

CATEGORY_LABELS = {
    "specialist": "частный специалист",
    "club": "фитнес-клуб или студия",
    "international": "международная организация",
    "client": "частный клиент",
}
VALID_CATEGORIES = tuple(CATEGORY_LABELS)


class CategoryStatus(StrEnum):
    """Статус определения категории."""

    CONFIDENT = "confident"  # категория определена уверенно
    AMBIGUOUS = "ambiguous"  # однозначно определить не удалось


@dataclass(frozen=True)
class CategoryDecision:
    """Результат классификации."""

    status: CategoryStatus
    category: str | None = None
    source: str = "keywords"  # keywords | ai | menu | fallback

    @property
    def is_confident(self) -> bool:
        return self.status == CategoryStatus.CONFIDENT


# --------------------------------------------------------------------- #
#  Ключевые слова категорий                                              #
# --------------------------------------------------------------------- #

KEYWORDS: dict[str, tuple[str, ...]] = {
    "specialist": (
        "тренер", "тренеров", "тренером", "тренерские",
        "инструктор", "инструктора", "инструктором",
        "обучение", "обучении", "обучиться", "обучениее",
        "курс", "курсы", "курса", "курсов",
        "matwork", "квалификацию", "квалификации",
        "сертифиц", "сертификацию", "сертификации",
        "лфк", "реабилитолог", "реабилитации",
        "профессию", "методике", "методику",
    ),
    "club": (
        "клуб", "клуба", "клубе", "клубом", "клубов",
        "студия", "студии", "студию", "студией",
        "фитнес-клуб", "фитнес центр", "фитнес-центра",
        "сотрудников", "сотрудники", "штат",
        "корпоративн", "команду тренеров", "команда тренеров",
        "персонал", "сеть клубов", "сети клубов",
    ),
    "international": (
        "international", "internationaln", "международн", "зарубежн",
        "за рубежом", "за границей", "foreign", "abroad", "overseas",
        "организация", "организации", "организацией",
        "conference", "конференци", "конгресс",
        "school", "academy abroad", "invite", "приглашен",
        "семинар для ", "европ", "america", "usa", "европе",
        "сша", "англи", "герман", "франц", "итали", "испани",
        "страна", "страны", "иностранн", "за рубежом", "abroad", "overseas",
    ),
    "client": (
        "персональные", "персональные тренировки", "персональных",
        "занятия для себя", "тренировки", "тренировках", "заниматься",
        "занятья", "занятие", "пробное", "пробных",
        "осанка", "осанке", "спина", "спине", "спиной", "боль",
        "боли", "боли в", "похудеть", "вес", "беремен", "фигуру",
        "начать заниматься", "для себя",
    ),
}


# Сильные фразы-якоря: однозначно указывают категорию целиком.
CONFIDENCE_RULES = {
    "specialist": (
        "хочу стать тренером", "я тренер", "работаю тренером",
        "работаю инструктором", "хочу освоить профессию",
    ),
    "club": (
        "представляю клуб", "представляю студию", "представляю фитнес-клуб",
        "я представляю клуб", "от имени клуба", "наш клуб", "мой клуб",
        "наша студия", "в нашем клубе", "у нас в клубе", "мы клуб",
        "обучить наших сотрудников", "для сотрудников нашего",
    ),
    "international": (
        "международная организация", "international organization",
        "за рубежом от имени", "приглашаем для проведения",
    ),
    "client": ("персональные тренировки для себя", "хочу записаться на тренировку"),
}


def classify_by_keywords(text: str) -> CategoryDecision:
    """Простая классификация по ключевым словам.

    Счёт категории — число различных слов текста, совпавших с её ключами
    (каждое слово учитывается один раз, чтобы «тренер» не считался дважды
    поверх «тренеров»). Одинаковое слово может засчитать нескольким
    категориям. Возвращает уверенную категорию, если счёт победителя хотя
    бы два и строго больше счёта ближайшего конкурента; иначе AMBIGUOUS.
    """

    lowered = (text or "").lower()
    # Сильные фразы-якоря имеют приоритет над общим счётом слов
    for category, anchors in CONFIDENCE_RULES.items():
        if any(anchor in lowered for anchor in anchors):
            return CategoryDecision(
                status=CategoryStatus.CONFIDENT, category=category, source="keywords"
            )

    tokens = re.findall(r"[\w-]+", lowered, flags=re.UNICODE)
    scores: dict[str, set[str]] = {}
    for category, words in KEYWORDS.items():
        for token in tokens:
            if any(word in token or token in word for word in words if len(word) > 3):
                scores.setdefault(category, set()).add(token)

    if not scores:
        return CategoryDecision(status=CategoryStatus.AMBIGUOUS)

    ordered = sorted(
        scores.items(), key=lambda kv: len(kv[1]), reverse=True
    )
    best_cat, best_tokens = ordered[0]
    best_score = len(best_tokens)
    runner_up = len(ordered[1][1]) if len(ordered) > 1 else 0
    if best_score >= 2 and best_score > runner_up:
        return CategoryDecision(
            status=CategoryStatus.CONFIDENT, category=best_cat, source="keywords"
        )
    return CategoryDecision(status=CategoryStatus.AMBIGUOUS)


async def classify_client(
    text: str,
    ai: OllamaClient,
    classify_prompt: str,
) -> CategoryDecision:
    """Определить категорию: сначала ключевые слова, затем AI-фолбэк.

    Никогда не бросает исключений; при полном провале — AMBIGUOUS,
    после которого менеджер задаёт уточняющий вопрос.
    """

    keyword_decision = classify_by_keywords(text)
    if keyword_decision.is_confident:
        return keyword_decision

    result = await ai.ask(
        text,
        system_prompt=classify_prompt,
        classify=True,
        max_tokens=8,
        timeout=45,
    )
    if isinstance(result, AIAnswer):
        code = result.text.strip().lower()
        if code in VALID_CATEGORIES:
            return CategoryDecision(
                status=CategoryStatus.CONFIDENT, category=code, source="ai"
            )
    else:
        # Классификация через AI не удалась — не блокируем диалог, но в лог
        logger_unavailable(result)
    return CategoryDecision(status=CategoryStatus.AMBIGUOUS)


def logger_unavailable(error: AIUnavailable) -> None:
    """Мягкое логирование недоступности AI (без секретов)."""

    import logging

    logging.getLogger(__name__).warning(
        "AI-классификация недоступна: %s (%s)", error.reason.value, error.detail[:120]
    )


CLARIFYING_QUESTION = (
    "Подскажите, пожалуйста, чтобы я рассказал о подходящей для вас программе: "
    "вы хотите освоить профессию тренера или повысить квалификацию (1), "
    "представляете фитнес-клуб или студию (2), "
    "выступаете от международной организации (3) "
    "или интересуетесь персональными тренировками (4)?"
)

MENU_REMINDER = (
    "Вы в любой момент можете вернуться в главное меню командой /menu "
    "и выбрать другое направление."
)


def is_category_button(payload_category: str | None) -> str | None:
    """Проверить payload кнопки выбора направления."""

    if payload_category in VALID_CATEGORIES:
        return payload_category
    return None


def normalize_menu_number(text: str) -> str | None:
    """Текст «1..4» или «направление N» из уточняющего вопроса."""

    match = re.search(r"\b([1-4])\b", text or "")
    if match:
        index = ("specialist", "club", "international", "client")
        return index[int(match.group(1)) - 1]
    return None


__all__ = [
    "CATEGORY_LABELS",
    "CLARIFYING_QUESTION",
    "CONFIDENCE_RULES",
    "CategoryDecision",
    "CategoryStatus",
    "MENU_REMINDER",
    "VALID_CATEGORIES",
    "classify_by_keywords",
    "classify_client",
    "is_category_button",
    "normalize_menu_number",
]