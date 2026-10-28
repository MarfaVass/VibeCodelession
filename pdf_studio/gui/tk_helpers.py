"""Стандартные шорткаты буфера обмена для полей ввода (Ctrl+V/C/X/A).

Причина отдельного модуля: в Tk по умолчанию Ctrl+V привязан к
латинскому keysym («Control-Key-v» → «Paste»). При активной русской
раскладке физическая клавиша V дает keysym «Cyrillic_*», латинская
привязка не срабатывает, и Ctrl+V/Ctrl+C/Ctrl+X «умирают» — известная
особенность Tk. Кроме того, Ctrl+A (выделить всё) в полях Tk не
привязан вовсе.

Решение: шорткаты подвешиваются на код клавиши (event.keycode), который
не зависит от выбранной раскладки: V=86, C=67, X=88, A=65
(virtual-key коды Windows). Обработчик выполняет действие и возвращает
«break», чтобы не допустить двойного срабатывания латинской привязки.
"""

import tkinter as tk
from tkinter import ttk

_CONTROL = 0x0004  # модификатор Control в event.state

# Код клавиши → действие (не зависит от раскладки).
_ACTIONS_BY_KEYCODE = {86: "paste", 67: "copy", 88: "cut", 65: "select_all"}


def action_for_keycode(keycode) -> str | None:
    """Действие для кода клавиши в сочетании с Ctrl, иначе None."""
    try:
        return _ACTIONS_BY_KEYCODE.get(int(keycode))
    except (TypeError, ValueError):
        return None


def _handle_shortcut(event):
    if not event.state & _CONTROL:
        return None
    action = action_for_keycode(event.keycode)
    if action is None:
        return None  # не наш шорткат — отдать событие дальше
    widget = event.widget
    if action == "paste":
        widget.event_generate("<<Paste>>")
    elif action == "copy":
        widget.event_generate("<<Copy>>")
    elif action == "cut":
        widget.event_generate("<<Cut>>")
    else:  # select_all
        widget.select_range(0, "end")
        widget.icursor("end")
    return "break"  # блокировать дублирующую привязку по keysym


def enable_entry_shortcuts(widget) -> None:
    """Включает Ctrl+V/Ctrl+C/Ctrl+X/Ctrl+A во всех Entry-полях окна.

    Работает при активной латинской и кириллической раскладке.
    """
    for child in widget.winfo_children():
        enable_entry_shortcuts(child)
    if isinstance(widget, (tk.Entry, ttk.Entry)):
        widget.bind("<Control-KeyPress>", _handle_shortcut, add="+")