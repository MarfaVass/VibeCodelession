# -*- coding: utf-8 -*-
"""Построение и сохранение диаграмм (matplotlib, режим Agg — только PNG).

Обе диаграммы считаются по выбранному месяцу на уровне ГРУПП и
сохраняются в корне проекта:
  * plan_vs_fact.png   — план vs факт по группам (группированные столбцы);
  * actual_expenses.png — структура фактических расходов по группам
    (круговая).

Цвет группы фиксированный: палитра задана по индексу группы в справочнике
data/categories.json, поэтому одна и та же группа — всегда одного цвета
на обеих диаграммах. План рисуется тем же цветом с прозрачностью,
факт — насыщенно. Палитра (11 оттенков) проверена на совместимость
с дальтонизмом; подкатегории на диаграммах не рисуются — их разрез
показывает таблица отчёта.
"""

from pathlib import Path
from typing import Dict, List, Optional

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
MUTED = "#898781"       # подписи осей и легенды
GRID = "#e1e0d9"        # линии сетки
BASELINE = "#c3c2b7"    # оси
UNKNOWN_COLOR = MUTED   # группа не из справочника (введённая ранее вручную)

# Палитра по индексу группы в справочнике — validated categorical palette
# (первые 9 оттенков занимают дефолтные группы; остальные — для новых).
CATALOG_PALETTE = [
    "#2a78d6",  # 1  Жильё        синий
    "#eb6834",  # 2  Здоровье     оранжевый
    "#1baf7a",  # 3  Одежда       аква
    "#eda100",  # 4  Развлечения  жёлтый
    "#e87ba4",  # 5  Обучение     розовый
    "#008300",  # 6  Связь        зелёный
    "#4a3aa7",  # 7  Транспорт    фиолетовый
    "#e34948",  # 8  Путешествия  красный
    "#5598e7",  # 9  Прочее       светло-синий
    "#d55181",  # 10 запасной
    "#c98500",  # 11 запасной
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
    """Подпись оси Y: 80 000 вместо 80000.

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


def group_color(catalog: Dict[str, List[str]], group: str) -> str:
    """Цвет группы по её индексу в справочнике.

    Группа не из справочника — нейтральный серый, чтобы она не выдавала
    себя за какую-то системную группу.

    :param catalog: справочник групп.
    :param group: название группы.
    """
    index = categories.group_color_index(catalog, group)
    if index < 0:
        return UNKNOWN_COLOR
    return CATALOG_PALETTE[index % len(CATALOG_PALETTE)]


# --- План-факт: столбчатая по группам --------------------------------------------
def build_plan_vs_fact(rows: List[Dict], catalog: Dict[str, List[str]],
                       month: str, path: Path = PLAN_VS_FACT_FILE) -> Optional[Path]:
    """Построить столбчатую диаграмму «план vs факт» по группам за месяц.

    План — светлый шаг цвета группы, факт — насыщенный.

    :param rows: строки reports.group_rows (group, plan, fact).
    :param catalog: справочник групп.
    :param month: ключ месяца «YYYY-MM» (в заголовок).
    :param path: куда сохранить PNG.
    :return: путь к файлу или None, если групп нет.
    """
    if not rows:
        return None
    names = [row["group"] for row in rows]
    positions = range(len(rows))

    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
    # подписи значений на каждом столбце избыточны — значения читаются по оси Y
    for row, pos in zip(rows, positions):
        color = group_color(catalog, row["group"])
        ax.bar(pos - BAR_PAIR_WIDTH / 2, row["plan"], width=BAR_PAIR_WIDTH,
               color=to_rgba(color, PLAN_ALPHA), edgecolor=SURFACE, linewidth=1.2, zorder=3)
        ax.bar(pos + BAR_PAIR_WIDTH / 2, row["fact"], width=BAR_PAIR_WIDTH,
               color=color, edgecolor=SURFACE, linewidth=1.2, zorder=3)

    ax.set_xticks(list(positions))
    ax.set_xticklabels(names, fontsize=9)
    ax.set_title(f"План и факт по группам — {month}", color=INK, pad=12)
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


# --- Факт: круговая по группам -----------------------------------------------------
def _slices_in_catalog_order(expense_entries: List[dict],
                             catalog: Dict[str, List[str]]) -> Dict[str, float]:
    """Суммы фактических расходов по группам в порядке справочника.

    Сектора идут в порядке data/categories.json; группы вне справочника —
    в конце по алфавиту. Мелкие лишние сектора (когда групп больше, чем
    цветов палитры) сворачиваются в «Прочее» (серый).

    :param expense_entries: записи фактических расходов месяца.
    :param catalog: справочник групп.
    :return: упорядоченный словарь {группа: сумма}.
    """
    totals: Dict[str, float] = {}
    for entry in expense_entries:
        name = str(entry.get(models.KEY_GROUP, "")).strip() or reports.UNKNOWN_ARTICLE_LABEL
        try:
            amount = float(entry.get(models.KEY_AMOUNT, 0.0))
        except (TypeError, ValueError):
            amount = 0.0
        totals[name] = totals.get(name, 0.0) + amount

    ordered: Dict[str, float] = {}
    for group in catalog:
        if totals.get(group, 0.0) > 0:
            ordered[group] = totals[group]
    leftover = sorted((name, amount) for name, amount in totals.items()
                      if amount > 0 and name not in ordered)

    max_slices = len(CATALOG_PALETTE)
    keep = max(0, max_slices - len(ordered) - 1)
    if len(ordered) + len(leftover) > max_slices:
        ordered.update(dict(leftover[:keep]))
        tail = leftover[keep:]
        if tail:
            ordered[reports.UNKNOWN_ARTICLE_LABEL] = sum(amount for _, amount in tail)
    else:
        ordered.update(dict(leftover))
    return ordered


def build_actual_expenses_pie(expense_entries: List[dict], catalog: Dict[str, List[str]],
                              path: Path = ACTUAL_EXPENSES_FILE) -> Optional[Path]:
    """Построить круговую диаграмму структуры факта по группам.

    Если фактических расходов за месяц нет — файл не создаётся
    (вызывающий код сообщит об этом пользователю).

    :param expense_entries: записи фактических расходов месяца.
    :param catalog: справочник групп.
    :param path: куда сохранить PNG.
    :return: путь к файлу или None, если трат нет.
    """
    slices = _slices_in_catalog_order(expense_entries, catalog)
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
        colors=[group_color(catalog, name) for name in slices],
        autopct=format_slice_pct,
        pctdistance=1.15,  # проценты за краем круга: тонкие сектора не переносятся
        startangle=90,
        counterclock=False,
        wedgeprops={"edgecolor": SURFACE, "linewidth": 2},  # зазор между секторами
        textprops={"fontsize": 9, "color": INK},
    )
    # названия групп — в легенде: у мелких секторов подписи вне круга слипаются
    ax.legend(wedges, legend_labels, loc="center left", bbox_to_anchor=(1.02, 0.5),
              frameon=False, fontsize=9)
    ax.set_title("Структура фактических расходов", color=INK, pad=12)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def build_charts(data: dict, month: str, catalog: Dict[str, List[str]] = None) -> List[Path]:
    """Построить обе диаграммы за месяц и вернуть пути к созданным PNG.

    Круговая строится только при наличии фактических расходов.

    :param data: структура бюджета.
    :param month: ключ месяца «YYYY-MM».
    :param catalog: справочник; None — загрузить из data/categories.json.
    :return: список сохранённых файлов.
    """
    if catalog is None:
        catalog = categories.load_categories()
    saved: List[Path] = []
    bar_path = build_plan_vs_fact(reports.group_rows(data, month), catalog, month)
    if bar_path is not None:
        saved.append(bar_path)
    pie_path = build_actual_expenses_pie(
        models.ensure_month(data, month)[models.KEY_ACTUAL_EXPENSES], catalog
    )
    if pie_path is not None:
        saved.append(pie_path)
    return saved
