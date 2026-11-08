# -*- coding: utf-8 -*-
"""Функции валидации пользовательского ввода.

Каждая ask_*-функция циклится до тех пор, пока не получит корректное
значение, и печатает понятное сообщение при каждой ошибке.
Консольный ввод — только здесь, чтобы остальной код оставался чистым.
"""

import math
import sys
from typing import Optional, Sequence, Tuple


def parse_amount(raw: str) -> Optional[float]:
    """Разобрать строку с суммой по строгим правилам.

    Правила: число строго больше нуля, разделитель — точка или запятая
    (99,50 -> 99.50), дробная часть — до двух знаков, сумма округляется.

    :param raw: строка, введённая пользователем.
    :return: сумма как float, либо None, если ввод некорректен.
    """
    if raw is None:
        return None
    cleaned = raw.strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(amount):
        return None
    if amount <= 0:
        return None
    return round(amount, 2)


def ask_amount(prompt: str) -> float:
    """Спросить сумму, повторяя вопрос до корректного ответа.

    :param prompt: текст приглашения.
    :return: положительная сумма.
    """
    while True:
        raw = input(f"{prompt} (в рублях, например 99,50): ")
        amount = parse_amount(raw)
        if amount is not None:
            return amount
        print("Ошибка: введите положительное число. Нечисловые значения, "
              "ноль и отрицательные суммы не допускаются.", file=sys.stderr)


def ask_non_empty(prompt: str) -> str:
    """Спросить непустую строку, повторяя вопрос до корректного ответа.

    :param prompt: текст приглашения.
    :return: строка без внешних пробелов и не пустая.
    """
    while True:
        raw = input(prompt).strip()
        if raw:
            return raw
        print("Ошибка: строка не может быть пустой.", file=sys.stderr)


def ask_choice(label: str, options: Sequence[Tuple[object, str]], prompt: str = None):
    """Спросить выбор из фиксированного списка вариантов.

    Используется для пунктов главного меню и вложенных подменю.

    :param label: что выбираем (для сообщений об ошибке).
    :param options: последовательность пар (выбранное_значение, описание).
    :param prompt: необязательный текст приглашения.
    :return: первый элемент выбранной пары.
    """
    menu_hint = prompt if prompt is not None else " ".join(
        f"[{value}] {description}" for value, description in options
    )
    known = {str(value) for value, _ in options}
    while True:
        raw = input(f"{menu_hint}\nВаш выбор {label}: ").strip()
        if raw in known:
            return next(value for value, _ in options if str(value) == raw)
        if raw == "":
            print(f"Ошибка: укажите {label}.", file=sys.stderr)
            continue
        print(f"Ошибка: {label} — только варианты из списка: {menu_hint}", file=sys.stderr)