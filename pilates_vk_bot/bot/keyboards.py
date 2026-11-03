"""Клавиатуры бота (vkbottle 4.x).

В vkbottle 4.11 текстовые кнопки собираются так:

    Keyboard().add(Text(label, payload), color=KeyboardButtonColor.X).row()...

Payload кнопок маршрутизирует действия: ``{"cmd": ...}`` — команда,
``{"category": ...}`` — выбор направления (единственный способ выбрать
категорию клиента).

Подписи кнопок конкретные и понятные — по результатам первого тестирования
аббревиатура «Другое направление» заменена на полное действие.
"""

from __future__ import annotations

from vkbottle import Keyboard, KeyboardButtonColor
from vkbottle.tools.keyboard.action import Text


def empty_keyboard() -> str:
    """Пустая клавиатура — убирает кнопки, когда они не нужны."""

    return Keyboard(one_time=False, inline=False).get_json()


def main_keyboard() -> str:
    """Главное меню: ровно четыре направления + справка.

    Подписи кнопок ограничены 40 символами (VKAPIError 911), поэтому
    формулировки направлений в меню короче полных названий веток.
    """

    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("Обучение инструкторов Pilates", {"category": "specialist"}))
    kb.row()
    kb.add(Text("Обучение команды клуба / студии", {"category": "club"}))
    kb.row()
    kb.add(Text("Пригласить инструктора", {"category": "international"}))
    kb.row()
    kb.add(Text("Персональные тренировки", {"category": "client"}))
    kb.row()
    kb.add(Text("Помощь", {"cmd": "/help"}))
    return kb.get_json()


def category_keyboard(category: str) -> str:
    """Клавиатура внутри направления: заявка и возврат в главное меню."""

    kb = Keyboard(one_time=False, inline=True)
    label = "Leave a request" if category == "international" else "Оставить заявку"
    kb.add(Text(label, {"cmd": "/book"}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text("Выбрать другое направление", {"cmd": "/menu"}))
    return kb.get_json()


def confirm_keyboard() -> str:
    """Клавиатура подтверждения заявки.

    Inline-клавиатуры VK не допускают ``one_time`` (VKAPIError 911),
    поэтому кнопки остаются до завершения сценария.
    """

    kb = Keyboard(one_time=False, inline=True)
    kb.add(Text("Отправить", {"cmd": "confirm_yes"}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text("Отменить", {"cmd": "/cancel"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


__all__ = [
    "category_keyboard",
    "confirm_keyboard",
    "empty_keyboard",
    "main_keyboard",
]