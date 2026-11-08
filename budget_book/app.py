# -*- coding: utf-8 -*-
"""Веб-интерфейс «Книги доходов и расходов» (Streamlit).

Запуск: streamlit run app.py   (из каталога budget_book)

Структура страницы: сверху — выбор месяца (применяется к плану и отчёту),
ниже вкладки «План», «Факт» и «Отчёт». Данные лежат в data/budget.json
по месяцам, справочник статей — в data/categories.json. Сумма вводится
number_input-ом с нижней границей 0 (отрицательные числа невозможны),
ноль трактуется как «поле не заполнено» и не сохраняется.
Streamlit-часть автоматически не тестируется — см. REPORT.md.
"""

from datetime import date

import streamlit as st

import categories
import charts
import models
import reports
import storage
import validators

MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

TITLE = "Книга доходов и расходов"

st.set_page_config(page_title=TITLE, page_icon=":bar_chart:", layout="wide")


# --- Вспомогательное ------------------------------------------------------------
def money(value: float) -> str:
    """Формат «80 000,00» для таблиц интерфейса.

    :param value: сумма.
    """
    return reports.format_money(value)


def month_label(key: str) -> str:
    """Человекочитаемый месяц: «2026-11» → «ноябрь 2026».

    :param key: ключ месяца «YYYY-MM».
    """
    year, month = models.parse_month_key(key)
    if 1 <= month <= 12:
        return f"{MONTH_NAMES[month - 1]} {year}".lower()
    return key


def number_to_float(value) -> float:
    """Сумму записи привести к float (ручные правки файла не ломают UI)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def available_months(data: dict) -> list:
    """Месяцы для выбора: известные в данных плюс текущий календарный.

    :param data: структура бюджета.
    :return: ключи «YYYY-MM» по возрастанию.
    """
    months = set(models.month_keys(data))
    today = date.today()
    months.add(models.month_key(today.year, today.month))
    return sorted(months)


def save_budget(data: dict) -> None:
    """Сохранить данные в файл сразу после изменения (модель: «кнопка = шаг»)."""
    storage.save_budget(data)


# --- Вкладка «План» ------------------------------------------------------------------
@st.dialog("Добавить плановый доход")
def add_planned_income_dialog(data: dict, key: str) -> None:
    """Диалог планового дохода: источник и сумма (месяц и год — выбранный месяц).

    Ноль и пустые поля не сохраняются: number_input ограничен снизу нулём,
    ноль трактуется как «поле не заполнено». Дата записи — выбранный месяц.

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    """
    source = st.text_input("Источник дохода", placeholder="Например, Зарплата")
    amount = st.number_input("Сумма, руб.", min_value=0.0, step=500.0, format="%.2f")
    if not st.button("Добавить доход", type="primary", use_container_width=True):
        return
    cleaned = validators.clean_text(source)
    if not cleaned:
        st.error("Поле «Источник дохода» пустое — не сохраняется.")
        return
    if amount <= 0:
        st.error("Сумма должна быть больше нуля — не сохраняется.")
        return
    block = models.ensure_month(data, key)
    block[models.KEY_PLANNED_INCOME].append(
        models.make_planned_income(cleaned, round(float(amount), 2)))
    save_budget(data)
    st.success(f"Доход «{cleaned}» запланирован на {month_label(key)}.")
    st.rerun()


@st.dialog("Добавить статью расходов")
def add_article_dialog(catalog: list) -> None:
    """Диалог добавления новой шаблонной статьи (дубликаты отклоняются).

    Новая статья сразу появляется в списке шаблонных и в справочнике
    data/categories.json — заём данных общий.

    :param catalog: текущий список статей.
    """
    name = st.text_input("Название статьи", placeholder="Например, Оптоволокно")
    if not st.button("Добавить статью", type="primary", use_container_width=True):
        return
    cleaned = validators.clean_text(name)
    if not cleaned:
        st.error("Поле пустое — не сохраняется.")
        return
    if categories.add_category(catalog, cleaned):
        st.success(f"Статья «{cleaned}» добавлена в шаблонные.")
        st.rerun()
    else:
        st.error("Такая категория уже есть.")


def render_planned_income(data: dict, key: str, block: dict) -> None:
    """Раздел плановых доходов: список и кнопка добавления.

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    :param block: блок выбранного месяца.
    """
    left, right = st.columns([2, 1])
    left.subheader("Плановый доход")
    if right.button("Добавить плановый доход", use_container_width=True):
        add_planned_income_dialog(data, key)
    st.caption("Запланированные поступления за выбранный месяц.")
    entries = block[models.KEY_PLANNED_INCOME]
    if not entries:
        st.caption("Плановых доходов нет.")
    for index, entry in enumerate(entries):
        remove, source, amount = st.columns([1, 6, 3])
        source.write(f"**{entry.get(models.KEY_SOURCE, '')}**")
        amount.write(f"{money(number_to_float(entry.get(models.KEY_AMOUNT)))} руб.")
        if remove.button("✕", key=f"income_delete_{key}_{index}",
                         help="Удалить плановый доход"):
            entries.pop(index)
            save_budget(data)
            st.rerun()


def render_articles_plan(data: dict, key: str, block: dict, catalog: list) -> None:
    """План по шаблонным статьям: поле суммы для каждой статьи + сохранение.

    Значение 0 (и все пустые) «убирает» статью из плана месяца —
    в JSON не сохраняются статьи с нулевыми суммами.

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    :param block: блок выбранного месяца.
    :param catalog: список статей из справочника.
    """
    planned_now = {
        entry.get(models.KEY_CATEGORY): number_to_float(entry.get(models.KEY_AMOUNT))
        for entry in block[models.KEY_PLANNED_ARTICLES]
    }
    left, _, right = st.columns([2, 4, 1])
    left.subheader("Шаблонные статьи")
    if right.button("Добавить статью расходов", use_container_width=True):
        add_article_dialog(catalog)
    st.caption(f"Сумма 0 — статья без плана. Месяц: {month_label(key)}.")

    with st.form(f"plan_articles_{key}", border=False):
        for index, article in enumerate(catalog):
            field_key = f"plan_{key}_{article}"
            if field_key not in st.session_state:
                st.session_state[field_key] = float(planned_now.get(article, 0.0))
            st.number_input(article, min_value=0.0, step=500.0, format="%.2f",
                            key=field_key)
        submitted = st.form_submit_button("Сохранить план по статьям", type="primary")
        if submitted:
            for article in catalog:
                amount = st.session_state.get(f"plan_{key}_{article}", 0.0)
                models.set_planned_article(block, article, round(float(amount), 2))
            save_budget(data)
            st.success(f"План по статьям за {month_label(key)} сохранён.")


# --- Вкладка «Факт» --------------------------------------------------------------------
@st.dialog("Добавить фактический расход")
def add_actual_expense_dialog(data: dict, key: str) -> None:
    """Диалог фактического расхода: сумма, дата, статья из списка, комментарий.

    Дата — полный день в пределах любого месяца (запись попадает
    в месяц даты, а отчёт и план листаются селектором выше).

    :param data: структура бюджета.
    :param key: ключ выбранного месяца (добавляется в подсказке).
    """
    amount = st.number_input("Сумма, руб.", min_value=0.0, step=100.0, format="%.2f")
    spent_on = st.date_input("Дата расхода", value="today", format="DD.MM.YYYY")
    catalog = categories.load_categories()
    category = st.selectbox("Статья расходов", catalog, index=0)
    comment = st.text_input("Комментарий", max_chars=120,
                            placeholder=f"Например, аренда за {month_label(key)}")

    if not st.button("Добавить расход", type="primary", use_container_width=True):
        return
    cleaned = validators.clean_text(comment)
    if amount <= 0:
        st.error("Сумма должна быть больше нуля — не сохраняется.")
        return
    if not cleaned:
        st.error("Комментарий пуст — не сохраняется.")
        return
    models.ensure_month(data, models.month_of_date(spent_on.isoformat()))[
        models.KEY_ACTUAL_EXPENSES
    ].append(models.make_actual_expense(
        category, cleaned, round(float(amount), 2), spent_on.isoformat()))
    save_budget(data)
    st.success(f"Расход добавлен ({spent_on.isoformat()}).")
    st.rerun()


def render_actual_expenses(data: dict, key: str, block: dict) -> None:
    """Список фактических расходов месяца с кнопками удаления.

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    :param block: блок выбранного месяца.
    """
    left, right = st.columns([2, 1])
    left.subheader("Фактический расход")
    if right.button("Добавить фактический расход", use_container_width=True):
        add_actual_expense_dialog(data, key)
    entries = block[models.KEY_ACTUAL_EXPENSES]
    if not entries:
        st.caption(f"Расходов за {month_label(key)} ещё нет.")
        return
    st.caption(f"Всего трат за {month_label(key)}: {len(entries)}")
    for index, entry in enumerate(entries):
        remove, category, comment, date_text, amount = st.columns([1, 3, 4, 2, 2])
        category.write(f"**{entry.get(models.KEY_CATEGORY, '')}**")
        comment.write(validators.clean_text(entry.get(models.KEY_COMMENT, "")) or "—")
        date_text.write(str(entry.get(models.KEY_DATE, "")))
        amount.write(f"{money(number_to_float(entry.get(models.KEY_AMOUNT)))} руб.")
        if remove.button("✕", key=f"expense_delete_{key}_{index}",
                         help="Удалить расход"):
            entries.pop(index)
            save_budget(data)
            st.rerun()


# --- Вкладка «Отчёт» ---------------------------------------------------------------------
def render_report_table(data: dict, key: str) -> None:
    """Сводка и таблица план-факт по статьям месяца.

    Процент — факт от плана; при нулевом плане прочерк «—».

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    """
    totals = reports.expenses_totals(data, key)
    income_col, plan_col, fact_col, balance_col = st.columns(4)
    income_col.metric("План доходов",
                      money(reports.income_total(data, key)),
                      help="Сумма плановых доходов за месяц")
    plan_col.metric("План расходов", money(totals["expenses_plan"]))
    fact_col.metric("Факт расходов", money(totals["expenses_fact"]))
    balance_col.metric("Остаток план",
                       money(totals["balance_plan"]),
                       help="Доходы (план) минус расходы (план)")

    st.subheader("План-факт по статьям")
    st.caption("Разница — план минус факт (положительная: расход меньше плана).")
    rows = reports.article_rows(data, key)
    if not rows:
        st.info(reports.NO_DATA)
        return
    st.table([
        {
            reports.ARTICLE_COLUMN: row["article"],
            "План": money(row["plan"]),
            "Факт": money(row["fact"]),
            "Разница": money(row["diff"]),
            "% от плана": (reports.PERCENT_DASH if row["percent"] is None
                           else f"{row["percent"] * 100:.1f}%"),
        }
        for row in rows
    ])


# --- Основной сценарий страницы ------------------------------------------------------------
def render_month_selector(data: dict) -> str:
    """Селектор месяца над вкладками: применяется к плану, факту и отчёту.

    :param data: структура бюджета.
    :return: выбранный ключ месяца «YYYY-MM».
    """
    today = date.today()
    months = available_months(data)
    picked = st.selectbox("Месяц", months, format_func=month_label,
                          index=months.index(models.month_key(today.year, today.month)))
    st.caption(f"Выбран месяц: **{month_label(picked)}** — применяется к плану и отчёту")
    return picked


def render_page() -> None:
    """Собрать страницу: выбор месяца, три вкладки, отчёт с диаграммами."""
    st.title(TITLE)
    data = storage.load_budget()
    month = render_month_selector(data)
    block = models.ensure_month(data, month)
    catalog = categories.load_categories()

    plan_tab, fact_tab, report_tab = st.tabs(["План", "Факт", "Отчёт"])

    with plan_tab:
        render_planned_income(data, month, block)
        st.divider()
        render_articles_plan(data, month, block, catalog)

    with fact_tab:
        render_actual_expenses(data, month, block)

    with report_tab:
        render_report_table(data, month)
        st.divider()
        st.subheader("Диаграммы")
        built = charts.build_charts(data, month, catalog)
        if charts.PLAN_VS_FACT_FILE in built:
            st.image(str(charts.PLAN_VS_FACT_FILE))
        else:
            st.info("Ни плана, ни факта по статьям — столбчатая диаграмма не построена.")
        if charts.ACTUAL_EXPENSES_FILE in built:
            st.image(str(charts.ACTUAL_EXPENSES_FILE))
        else:
            st.info("Фактических расходов за месяц нет — круговая диаграмма не построена.")


render_page()
