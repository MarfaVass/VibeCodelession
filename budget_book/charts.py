# -*- coding: utf-8 -*-
"""Построение и сохранение диаграмм (matplotlib, режим Agg — только PNG).

Обе диаграммы — статические PNG в корне проекта:
  * plan_vs_fact.png   — план vs факт по категориям (группированные столбцы);
  * actual_expenses.png — структура фактических расходов (круговая).

Цвет по категории фиксированный: палитра в charts.py задана по индексу
категории в справочнике data/categories.json, поэтому одна и та же
категория — всегда одного цвета на обеих диаграммах. Доходные пары —
нейтральный серый: их цвет не «крадёт» цвет расходной категории.
План рисуется тем же цветом категории с прозрачностью, факт — насыщенно.
Палитра проверена на совместимость с дальтонизмом (CVD-валидатор).
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")  # без GUI: только сохраняем файлы
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import to_rgba  # noqa: E402 — после matplotlib.use()
from matplotlib.ticker import FuncFormatter  # noqa: E402 — после matplotlib.use()

import categories
import models
import reports

# --- Оформление «холста» -------------------------------------------------------
SURFACE = "#fcfcfb"     # поверхность графика
INK = "#0b0b0b"         # основной текст
MUTED = "#898781"       # подписи осей, легенды и «неизвестные» категории
GRID = "#e1e0d9"        # линии сетки
BASELINE = "#c3c2b7"    # оси; нейтральный «план» доходных пар

INCOME_PAIR_COLORS = (BASELINE, MUTED)  # (план, факт) для доходов
UNKNOWN_COLOR = MUTED   # категория не из справочника (данные, введённые ранее)

# Палитра по индексу категории в справочнике — validated categorical palette,
# расширенная тремя шагами тех же оттенков и прогнанная через валидатор.
CATALOG_PALETTE = [
    "#2a78d6",  # 1  Жильё              синий
    "#eb6834",  # 2  Продукты           оранжевый
    "#1baf7a",  # 3  Транспорт          аква
    "#eda100",  # 4  Здоровье           жёлтый
    "#e87ba4",  # 5  Образование        розовый
    "#008300",  # 6  Развлечения        зелёный
    "#4a3aa7",  # 7  Одежда             фиолетовый
    "#e34948",  # 8  Связь и интернет   красный
    "#5598e7",  # 9  Подписки           светло-синий
    "#d55181",  # 10 Подарки            тёмно-розовый
    "#c98500",  # 11 Прочее             тёмно-янтарный
]
PLAN_ALPHA = 0.35       # план — тот же оттенок, но светлее (прозрачность)
MIN_PCT_LABEL = 3.0     # проценты меньше этого не подписываем (сектора мелкие)
BAR_PAIR_WIDTH = 0.38   # ширина одного столбца в паре

PROJECT_ROOT = Path(__file__).resolve().parent
PLAN_VS_FACT_FILE = PROJECT_ROOT / "plan_vs_fact.png"
ACTUAL_EXPENSES_FILE = PROJECT_ROOT / "actual_expenses.png"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "text.color": INK,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": MUTED,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
})


def _money_formatter(value, _pos) -> str:
    """Подписи оси Y: 80 000 вместо 80000.

    :param value: значение по оси.
    :param _pos: позиция деления (не используется).
    """
    return f"{value:,.0f}".replace(",", " ")


def _clean_axes(ax) -> None:
    """Убрать лишнее обрамление и оставить тонкую горизонтальную сетку."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def category_color(catalog: List[str], name: str) -> str:
    """Цвет категории по её индексу в справочнике.

    Категория не из справочника — нейтральный серый, чтобы она
    не выдавала себя за какую-то системную категорию.

    :param catalog: список категорий.
    :param name: название категории.
    :return: hex-цвет.
    """
    try:
        index = catalog.index(name)
    except ValueError:
        return UNKNOWN_COLOR
    return CATALOG_PALETTE[index % len(CATALOG_PALETTE)]


def _row_pair(catalog: List[str], row: Dict) -> Tuple[str, str]:
    """Цвет (план, факт) для строки отчёта.

    Доходные строки (не из расходного справочника) — нейтральный серый.

    :param catalog: список категорий.
    :param row: {category, plan, fact}.
    """
    if row.get("is_income"):
        return INCOME_PAIR_COLORS
    color = category_color(catalog, row["category"])
    lighter = to_rgba(color, PLAN_ALPHA)
    return (lighter, color)


# --- План-факт: столбчатая -------------------------------------------------------
def build_plan_vs_fact(data: dict, catalog: List[str], path: Path = PLAN_VS_FACT_FILE) -> Optional[Path]:
    """Построить столбчатую диаграмму «план vs факт» по категориям.

    Доходные категории — нейтральными парами, расходные — в цвет
    категории из справочника (план светлее, факт насыщеннее).

    :param data: структура бюджета.
    :param catalog: список категорий.
    :param path: куда сохранить PNG.
    :return: путь к файлу или None, если категорий нет.
    """
    expense = [{**row, "is_income": False} for row in reports.expense_rows(data)]
    income = [{**row, "is_income": True} for row in reports.income_rows(data)]
    rows = income + expense
    if not rows:
        return None

    names = [row["category"] for row in rows]
    positions = range(len(rows))

    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
    plan_lefts = [pos - BAR_PAIR_WIDTH / 2 for pos in positions]
    fact_lefts = [pos + BAR_PAIR_WIDTH / 2 for pos in positions]
    for row, left_plan, left_fact in zip(rows, plan_lefts, fact_lefts):
        color_plan, color_fact = _row_pair(catalog, row)
        ax.bar(left_plan, row["plan"], width=BAR_PAIR_WIDTH, color=color_plan,
               edgecolor=SURFACE, linewidth=1.2, zorder=3)
        ax.bar(left_fact, row["fact"], width=BAR_PAIR_WIDTH, color=color_fact,
               edgecolor=SURFACE, linewidth=1.2, zorder=3)

    ax.set_xticks(list(positions))
    ax.set_xticklabels(names, fontsize=9)
    ax.set_title("План и факт по категориям", color=INK, pad=12)
    ax.set_ylabel("Сумма, руб.")
    ax.yaxis.set_major_formatter(FuncFormatter(_money_formatter))
    _clean_axes(ax)
    legend_handles = [
        mpatches.Patch(fc=BASELINE, alpha=PLAN_ALPHA, label="План (светлее)"),
        mpatches.Patch(fc=MUTED, label="Факт (насыщеннее)"),
    ]
    ax.legend(handles=legend_handles, frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


# --- Факт: круговая ----------------------------------------------------------------
def _slice_amounts(data: dict, catalog: List[str]) -> Dict[str, float]:
    """Суммы фактических расходов в порядке справочника.

    Сектора идут в порядке data/categories.json; категории вне справочника —
    в конце по алфавиту. Мелкие лишние сектора, когда категорий больше,
    чем цветов палитры, сворачиваются в «Прочее» (серый).

    :param data: структура бюджета.
    :param catalog: список категорий.
    :return: упорядоченный словарь {категория: сумма}.
    """
    totals: Dict[str, float] = {}
    for entry in data[models.KEY_ACTUAL_EXPENSES]:
        name = str(entry.get("category", "")).strip() or reports.OTHER_CATEGORY_LABEL
        try:
            amount = float(entry.get("amount", 0.0))
        except (TypeError, ValueError):
            amount = 0.0
        totals[name] = totals.get(name, 0.0) + amount

    ordered: Dict[str, float] = {}
    for name in catalog:
        if totals.get(name, 0.0) > 0:
            ordered[name] = totals[name]
    leftover = sorted((name, amount) for name, amount in totals.items()
                      if amount > 0 and name not in ordered)

    max_slices = len(CATALOG_PALETTE)
    keep = max(0, max_slices - len(ordered) - 1)
    if len(ordered) + len(leftover) > max_slices:
        head, tail = leftover[:keep], leftover[keep:]
        ordered.update(dict(head))
        if tail:
            ordered[reports.OTHER_CATEGORY_LABEL] = sum(amount for _, amount in tail)
    else:
        ordered.update(dict(leftover))
    return ordered


def build_actual_expenses_pie(data: dict, catalog: List[str], path: Path = ACTUAL_EXPENSES_FILE) -> Optional[Path]:
    """Построить круговую диаграмму структуры фактических расходов.

    Если фактических расходов нет — файл не создаётся (вызывающий код
    должен сообщить об этом пользователю).

    :param data: структура бюджета.
    :param catalog: список категорий.
    :param path: куда сохранить PNG.
    :return: путь к файлу или None, если трат нет.
    """
    slices = _slice_amounts(data, catalog)
    if not slices:
        return None

    def format_slice_pct(pct: float) -> str:
        """Подпись сектора в %, скрытая у слишком мелких секторов."""
        return f"{pct:.1f}%" if pct >= MIN_PCT_LABEL else ""

    legend_labels = [
        f"{name} — {reports.format_money(amount)}" for name, amount in slices.items()
    ]
    fig, ax = plt.subplots(figsize=(8.4, 5.6), dpi=150)
    wedges, _slice_labels, _pct_texts = ax.pie(
        list(slices.values()),
        colors=[category_color(catalog, name) for name in slices],
        autopct=format_slice_pct,
        pctdistance=1.15,  # проценты за краем круга: тонкие сектора не переносятся
        startangle=90,
        counterclock=False,
        wedgeprops={"edgecolor": SURFACE, "linewidth": 2},  # зазор между секторами
        textprops={"fontsize": 9, "color": INK},
    )
    # названия категорий — в легенде: у мелких секторов подписи вне круга слипаются
    ax.legend(wedges, legend_labels, loc="center left", bbox_to_anchor=(1.02, 0.5),
              frameon=False, fontsize=9)
    ax.set_title("Структура фактических расходов", color=INK, pad=12)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def build_charts(data: dict, catalog: List[str] = None) -> List[Path]:
    """Построить обе диаграммы и вернуть пути к созданным PNG.

    Круговая строится только при наличии фактических расходов.

    :param data: структура бюджета.
    :param catalog: список категорий; None — загрузить из data/categories.json.
    :return: список сохранённых файлов.
    """
    if catalog is None:
        catalog = categories.load_categories()
    saved: List[Path] = []
    bar_path = build_plan_vs_fact(data, catalog)
    if bar_path is not None:
        saved.append(bar_path)
    pie_path = build_actual_expenses_pie(data, catalog)
    if pie_path is not None:
        saved.append(pie_path)
    return saved
