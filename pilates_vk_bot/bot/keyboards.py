"""Клавиатуры бота (vkbottle 4.x).

В vkbottle 4.11 текстовые кнопки собираются так:

    Keyboard().add(Text(label, payload), color=KeyboardButtonColor.X).row()...

Payload кнопок маршрутизирует команды: ``{"cmd": "/book"}`` — действие,
``{"category": "client"}`` — выбор направления.
"""

from __future__ import annotations

from vkbottle import Keyboard, KeyboardButtonColor
from vkbottle.tools.keyboard.action import Text

CMDS = {
    "menu": "/menu",
    "help": "/help",
    "book": "/book",
    "cancel": "/cancel",
}


def empty_keyboard() -> str:
    """Пустая клавиатура — убирает кнопки, когда они не нужны."""

    return Keyboard(one_time=False, inline=False).get_json()


def main_keyboard() -> str:
    """Главное меню: четыре направления + заявка и справка."""

    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("Я хочу стать тренером или повысить квалификацию", {"category": "specialist"}))
    kb.row()
    kb.add(Text("Я представляю фитнес-клуб или студию", {"category": "club"}))
    kb.row()
    kb.add(Text("Я представляю международную организацию", {"category": "international"}))
    kb.row()
    kb.add(Text("Меня интересуют персональные тренировки", {"category": "client"}))
    kb.row()
    kb.add(
        Text("Оставить заявку", {"cmd": "/book"}),
        color=KeyboardButtonColor.POSITIVE,
    ).add(Text("Помощь", {"cmd": "/help"}))
    return kb.get_json()


def category_keyboard(category: str) -> str:
    """Клавиатура внутри направления: заявка, справка, меню."""

    kb = Keyboard(one_time=False, inline=True)
    label = "Leave a request" if category == "international" else "Оставить заявку"
    kb.add(Text(label, {"cmd": "/book"}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text("Другое направление", {"cmd": "/menu"}))
    return kb.get_json()


def confirm_keyboard() -> str:
    """Клавиатура подтверждения заявки."""

    kb = Keyboard(one_time=True, inline=True)
    kb.add(Text("Отправить", {"cmd": "confirm_yes"}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text("Отменить", {"cmd": "/cancel"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


__all__ = [
    "category_keyboard",
    "confirm_keyboard",
    "empty_keyboard",
    "main_keyboard",
]