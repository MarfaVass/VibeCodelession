# -*- coding: utf-8 -*-
"""Веб-интерфейс «Книги доходов и расходов» (Streamlit).

Запуск: streamlit run app.py   (из каталога budget_book)

Структура страницы: сверху — выбор месяца (применяется к плану, фактам
и отчёту), ниже вкладки «План», «Факт», «Отчёт» и «Категории».
Категории двухуровневые (группа → подкатегория), справочник —
data/categories.json, данные по месяцам — data/budget.json.

Деньги «на виду»: на вкладке «План» сразу видно входящий остаток,
плановые доходы (зарплата, подработка, прочий доход), суммарный план
расходов и свободный остаток (перерасход подсвечивается). На вкладке
«Факт» та же сводка сверху считается по факту трат.

Сумма вводится number_input-ом с нижней границей 0 (отрицательные суммы
невозможны); ноль трактуется как «поле не заполнено» и не сохраняется.
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
NO_SUBCATEGORY_LABEL = reports.NO_SUBCATEGORY_LABEL

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


def money_summary(data: dict, month: str) -> dict:
    """Сводка «денег на виду» для вкладок «План» и «Факт».

    :param data: структура бюджета.
    :param month: ключ месяца.
    :return: {carryover, income_plan, expenses_plan, expenses_fact,
              free_plan, free_fact}.
    """
    block = models.ensure_month(data, month)
    totals = reports.expenses_totals(data, month)
    carryover = models.get_carryover(block)
    income_plan = reports.income_total(data, month)
    return {
        "carryover": carryover,
        "income_plan": income_plan,
        "expenses_plan": totals["expenses_plan"],
        "expenses_fact": totals["expenses_fact"],
        "free_plan": carryover + income_plan - totals["expenses_plan"],
        "free_fact": carryover + income_plan - totals["expenses_fact"],
    }


# --- Вкладка «План» ------------------------------------------------------------------
@st.dialog("Добавить плановый доход")
def add_custom_income_dialog(data: dict, key: str) -> None:
    """Диалог прочего планового дохода с произвольным источником.

    Зарплата/подработка/прочий доход вводятся быстрее — через поля
    на странице; этот диалог для остальных источников.

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    """
    source = st.text_input("Источник дохода", placeholder="Например, Премия")
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
    models.set_planned_income(block, cleaned, round(float(amount), 2))
    storage.save_budget(data)
    st.success(f"Доход «{cleaned}» запланирован на {month_label(key)}.")
    st.rerun()


def render_plan_money_row(data: dict, key: str, block: dict) -> dict:
    """Сводка страницы плана: входящий остаток и живой счёт денег.

    Входящий остаток — редактируемое поле (сохраняется сразу при
    изменении). Свободные деньги — входящий остаток + плановые доходы
    минус план статей; отрицательное значение подсвечивается.

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    :param block: блок выбранного месяца.
    :return: словарь money_summary (для остальных блоков страницы).
    """
    carryover_key = f"carryover_{key}"
    if carryover_key not in st.session_state:
        st.session_state[carryover_key] = float(models.get_carryover(block))
    carryover_value = st.number_input(
        "Входящий остаток (с прошлых месяцев)", min_value=None,
        step=500.0, format="%.2f", key=carryover_key)
    if round(float(carryover_value), 2) != models.get_carryover(block):
        models.set_carryover(block, float(carryover_value))
        storage.save_budget(data)

    summary = money_summary(data, key)
    income_col, plan_col, free_col = st.columns(3)
    income_col.metric("Плановый доход",
                      money(summary["income_plan"]),
                      help="Зарплата, подработка, прочий доход — ниже")
    plan_col.metric("План расходов",
                    money(summary["expenses_plan"]),
                    help="Сумма планов по статьям ниже")
    free_col.metric("Свободно (остаток + доходы − план)",
                    money(summary["free_plan"]))
    if summary["free_plan"] < 0:
        st.error(f"Плановый перерасход на {money(-summary['free_plan'])} руб. "
                 "— сократи план или доходы.")
    return summary


def render_quick_income(data: dict, key: str, block: dict) -> None:
    """Быстрые поля планового дохода: зарплата, подработка, прочий доход.

    Каждое поле заменяет прежнюю сумму по источнику; ноль — источник
    без плана. Плюс кнопка для произвольного источника.

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    :param block: блок выбранного месяца.
    """
    actual_sources = {
        str(entry.get(models.KEY_SOURCE, "")): number_to_float(entry.get(models.KEY_AMOUNT))
        for entry in block[models.KEY_PLANNED_INCOME]
    }
    left, right = st.columns([2, 1])
    left.subheader("Плановый доход")
    if right.button("Другой источник…", use_container_width=True):
        add_custom_income_dialog(data, key)

    with st.form(f"quick_income_{key}", border=False):
        columns = st.columns(len(models.QUICK_INCOME_SOURCES))
        for column, source in zip(columns, models.QUICK_INCOME_SOURCES):
            field_key = f"income_{key}_{source}"
            if field_key not in st.session_state:
                st.session_state[field_key] = float(actual_sources.get(source, 0.0))
            column.number_input(source, min_value=0.0, step=1000.0, format="%.2f",
                                key=field_key)
        if st.form_submit_button("Сохранить плановый доход", type="primary"):
            for source in models.QUICK_INCOME_SOURCES:
                amount = round(float(st.session_state.get(f"income_{key}_{source}", 0.0)), 2)
                models.set_planned_income(block, source, amount)
            storage.save_budget(data)
            st.success(f"Плановый доход за {month_label(key)} сохранён.")


@st.dialog("Добавить статью расходов")
def add_article_dialog(catalog: dict) -> None:
    """Диалог добавления: новую группу (сразу с подкатегориями) или
    подкатегорию в существующую группу. Дубликаты отклоняются.

    :param catalog: двухуровневый справочник.
    """
    mode = st.radio("Что добавить", ["Группу", "Подкатегорию в группу"])
    if mode == "Группу":
        group = st.text_input("Название группы", placeholder="Например, Питомцы")
        subs_text = st.text_area(
            "Подкатегории (необязательно; по одной на строку)",
            help="Можно добавить и позже — через этот же диалог.")
        if not st.button("Добавить группу", type="primary", use_container_width=True):
            return
        cleaned = validators.clean_text(group)
        if not cleaned:
            st.error("Название пустое — не сохраняется.")
            return
        subs = [validators.clean_text(line) for line in subs_text.splitlines()]
        result = categories.add_group(catalog, cleaned, [s for s in subs if s])
        if result == categories.DUPLICATE:
            st.error("Такая категория уже есть.")
        else:
            st.success(f"Группа «{cleaned}» добавлена в шаблонные.")
            st.rerun()
    else:
        group = st.selectbox("Группа", categories.group_names(catalog))
        name = st.text_input("Название подкатегории",
                             placeholder="Например, Корм и наполнитель")
        if not st.button("Добавить подкатегорию", type="primary", use_container_width=True):
            return
        cleaned = validators.clean_text(name)
        if not cleaned:
            st.error("Название пустое — не сохраняется.")
            return
        result = categories.add_subcategory(catalog, group, cleaned)
        if result == categories.DUPLICATE:
            st.error("Такая категория уже есть.")
        elif result == categories.NO_GROUP:
            st.error("Группа не найдена — обновите список.")
        else:
            st.success(f"«{cleaned}» добавлена в группу «{group}».")
            st.rerun()


def render_articles_plan(data: dict, key: str, block: dict, catalog: dict) -> None:
    """План по шаблонным статьям: для каждой группы — заголовок,
    под ним поля сумм по подкатегориям.

    Значение 0 (и все пустые) «убирает» запись из плана месяца —
    нулевые суммы в JSON не сохраняются.

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    :param block: блок выбранного месяца.
    :param catalog: двухуровневый справочник.
    """
    planned_now = {
        (str(entry.get(models.KEY_GROUP, "")), str(entry.get(models.KEY_CATEGORY, ""))):
            number_to_float(entry.get(models.KEY_AMOUNT))
        for entry in block[models.KEY_PLANNED_ARTICLES]
    }
    st.subheader("План по статьям")
    st.caption(f"Сумма 0 — статья без плана. Месяц: {month_label(key)}. "
               "Новые статьи добавляются на вкладке «Категории».")

    with st.form(f"plan_articles_{key}", border=False):
        for group, subs in catalog.items():
            st.markdown(f"**{group}**")
            for sub in subs or [None]:  # пустая группа — план на группу целиком
                field_key = f"plan_{key}_{group}_{sub or 'GROUP'}"
                if field_key not in st.session_state:
                    st.session_state[field_key] = float(planned_now.get((group, sub or ""), 0.0))
                st.number_input(sub or f"{group} {NO_SUBCATEGORY_LABEL}",
                                min_value=0.0, step=500.0, format="%.2f", key=field_key)
        submitted = st.form_submit_button("Сохранить план по статьям", type="primary")
        if submitted:
            for group, subs in catalog.items():
                for sub in subs or [None]:
                    field_key = f"plan_{key}_{group}_{sub or 'GROUP'}"
                    amount = round(float(st.session_state.get(field_key, 0.0)), 2)
                    models.set_planned_article(block, group, sub or "", amount)
            storage.save_budget(data)
            st.success(f"План по статьям за {month_label(key)} сохранён.")


# --- Вкладка «Факт» --------------------------------------------------------------------
@st.dialog("Добавить фактический расход")
def add_actual_expense_dialog(data: dict, key: str) -> None:
    """Диалог фактического расхода: группа → подкатегория (зависимые
    списки), сумма, дата, комментарий. Сводка денег повторяется сверху.

    Дата — полный день в любом месяце (запись попадает в свой месяц,
    а вкладки показывают выбранный селектором).

    :param data: структура бюджета.
    :param key: ключ выбранного месяца (для подсказки).
    """
    summary = money_summary(data, key)
    col_money, col_free = st.columns(2)
    col_money.metric("Плановый доход", money(summary["income_plan"]))
    col_free.metric("Остаток (доход − факт трат)", money(summary["free_fact"]))

    amount = st.number_input("Сумма расхода, руб.", min_value=0.0, step=100.0, format="%.2f")
    spent_on = st.date_input("Дата расхода", value="today", format="DD.MM.YYYY")
    catalog = categories.load_categories()
    group = st.selectbox("Группа", categories.group_names(catalog))
    sub = st.selectbox("Подкатегория",
                       catalog.get(group, []) or [NO_SUBCATEGORY_LABEL])
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
    spent_month = models.month_of_date(spent_on.isoformat())
    block = models.ensure_month(data, spent_month)
    block[models.KEY_ACTUAL_EXPENSES].append(models.make_actual_expense(
        group, "" if sub == NO_SUBCATEGORY_LABEL else sub, cleaned,
        round(float(amount), 2), spent_on.isoformat()))
    storage.save_budget(data)
    after = money_summary(data, key)
    st.success(f"Расход добавлен. Остаток (доход − факт трат): {money(after['free_fact'])} руб.")
    st.rerun()


def render_actual_expenses(data: dict, key: str, block: dict) -> None:
    """Вкладка «Факт»: сводка сверху, список трат и кнопка добавления.

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    :param block: блок выбранного месяца.
    """
    summary = money_summary(data, key)
    carryover_col, income_col, fact_col, rest_col = st.columns(4)
    carryover_col.metric("Входящий остаток", money(summary["carryover"]))
    income_col.metric("Плановый доход", money(summary["income_plan"]))
    fact_col.metric("Факт расходов", money(summary["expenses_fact"]))
    rest_col.metric("Остаток (доход − расход)", money(summary["free_fact"]))
    if summary["free_fact"] < 0:
        st.error(f"Расходы превысили доступные деньги на "
                 f"{money(-summary['free_fact'])} руб.")

    left, right = st.columns([2, 1])
    left.subheader("Список трат")
    if right.button("Добавить фактический расход", use_container_width=True):
        add_actual_expense_dialog(data, key)
    entries = block[models.KEY_ACTUAL_EXPENSES]
    if not entries:
        st.caption(f"Расходов за {month_label(key)} ещё нет.")
        return
    for index, entry in enumerate(entries):
        remove, article, comment, date_text, amount = st.columns([1, 3, 4, 2, 2])
        article.write(f"**{models.entry_label(entry)}**")
        comment.write(validators.clean_text(entry.get(models.KEY_COMMENT, "")) or "—")
        date_text.write(str(entry.get(models.KEY_DATE, "")))
        amount.write(f"{money(number_to_float(entry.get(models.KEY_AMOUNT)))} руб.")
        if remove.button("✕", key=f"expense_delete_{key}_{index}",
                         help="Удалить расход"):
            entries.pop(index)
            storage.save_budget(data)
            st.rerun()


# --- Вкладка «Отчёт» ---------------------------------------------------------------------
def render_report_table(data: dict, key: str) -> None:
    """Отчёт: сводка, компактная таблица групп, план-факт по группам
    с раскрытием подкатегорий (expander у каждой группы).

    :param data: структура бюджета.
    :param key: ключ выбранного месяца.
    """
    summary = money_summary(data, key)
    carryover_col, income_col, plan_col, fact_col, rest_col = st.columns(5)
    carryover_col.metric("Входящий остаток", money(summary["carryover"]))
    income_col.metric("План доходов", money(summary["income_plan"]))
    plan_col.metric("План расходов", money(summary["expenses_plan"]))
    fact_col.metric("Факт расходов", money(summary["expenses_fact"]))
    rest_col.metric("Свободно факт", money(summary["free_fact"]),
                    help="Остаток + доходы (план) − факт трат")

    st.subheader("План-факт по группам")
    st.caption("Разница — план минус факт (положительная: расход меньше плана).")
    rows = reports.group_rows(data, key)
    if not rows:
        st.info(reports.NO_DATA)
        return

    st.table([{
        reports.GROUP_COLUMN: row["group"],
        "План": money(row["plan"]),
        "Факт": money(row["fact"]),
        "Разница": money(row["diff"]),
        "% от плана": (reports.PERCENT_DASH if row["percent"] is None
                       else f"{row["percent"] * 100:.1f}%"),
    } for row in rows])

    st.subheader("Раскрытие по подкатегориям")
    for row in rows:
        subs = reports.sub_rows(data, key, row["group"])
        header = (f"{row['group']}: план {money(row['plan'])}, факт {money(row['fact'])}")
        with st.expander(header):
            if not subs:
                st.caption(reports.NO_DATA)
                continue
            st.table([{
                reports.SUB_COLUMN: sub["sub"] or NO_SUBCATEGORY_LABEL,
                "План": money(sub["plan"]),
                "Факт": money(sub["fact"]),
                "Разница": money(sub["diff"]),
                "% от плана": (reports.PERCENT_DASH if sub["percent"] is None
                               else f"{sub["percent"] * 100:.1f}%"),
            } for sub in subs])


# --- Вкладка «Категории» ---------------------------------------------------------------------
def render_categories_tree(catalog: dict) -> None:
    """Показать справочник: все группы с подкатегориями.

    :param catalog: двухуровневый справочник.
    """
    st.caption(f"Групп: {len(catalog)}. Порядок групп задаёт порядок строк "
               "отчёта и цвета диаграмм.")
    for group, subs in catalog.items():
        st.markdown(f"**{group}**")
        if subs:
            st.markdown("  \n".join(f"· {sub}" for sub in subs))
        else:
            st.caption(NO_SUBCATEGORY_LABEL)


@st.dialog("Удалить статью")
def delete_article_dialog(data: dict, catalog: dict) -> None:
    """Диалог удаления группы или подкатегории.

    Если по статье уже есть планы или факты, записи автоматически
    переносятся в группу «Прочее» как подкатегория с тем же названием —
    данные не теряются (решение описано в REPORT.md). Группа «Прочее»
    не удаляется: это приёмник переноса.

    :param data: структура бюджета.
    :param catalog: двухуровневый справочник.
    """
    mode = st.radio("Что удалить", ["Подкатегорию", "Группу"])
    group = st.selectbox("Группа", categories.group_names(catalog))
    if mode == "Подкатегорию":
        subs = catalog.get(group, [])
        if not subs:
            st.error("У группы нет подкатегорий.")
            return
        sub = st.selectbox("Подкатегория", subs)
        target = "«" + sub + "» (из группы «" + group + "»)"
    else:
        if group == models.KEY_UNKNOWN_GROUP:
            st.error("Группу «Прочее» удалить нельзя — в неё переносятся записи "
                     "удаляемых статей.")
            return
        sub = None
        target = f"группу «{group}» целиком, вместе с подкатегориями"

    usage = models.count_article_usage(data, group, sub)
    if usage:
        st.warning(f"По статье записей: {usage}. Они будут переведены в «Прочее» "
                   "как подкатегория с тем же названием.")
    if not st.button("Удалить", type="primary", use_container_width=True):
        return
    moved = models.relocate_article_entries(data, group, sub)
    for name in moved:
        categories.add_subcategory(catalog, models.KEY_UNKNOWN_GROUP, name, path=None)
    result = (categories.remove_subcategory(catalog, group, sub) if sub is not None
              else categories.remove_group(catalog, group))
    if result != categories.REMOVED:
        st.error("Статья не найдена — возможно, уже удалена.")
        return
    categories.save_categories(catalog)
    storage.save_budget(data)
    st.success(f"Удалено: {target}.")
    st.rerun()


def render_categories_tab(data: dict) -> None:
    """Вкладка «Категории»: справочник и добавление/удаление статей.

    :param data: структура бюджета.
    """
    left, right = st.columns(2)
    with left:
        st.markdown("#### Действия")
        if st.button("Добавить группу или подкатегорию", use_container_width=True):
            add_article_dialog(categories.load_categories())
        if st.button("Удалить группу или подкатегорию", use_container_width=True):
            delete_article_dialog(data, categories.load_categories())
    st.divider()
    st.markdown("#### Справочник")
    render_categories_tree(categories.load_categories())


# --- Основной сценарий страницы ------------------------------------------------------------
def render_month_selector(data: dict) -> str:
    """Селектор месяца над вкладками: применяется к плану, фактам и отчёту.

    :param data: структура бюджета.
    :return: выбранный ключ месяца «YYYY-MM».
    """
    today = date.today()
    months = available_months(data)
    picked = st.selectbox(
        "Месяц", months, format_func=month_label,
        index=months.index(models.month_key(today.year, today.month)))
    st.caption(f"Выбран месяц: **{month_label(picked)}** — применяется к плану и отчёту")
    return picked


def render_page() -> None:
    """Собрать страницу: выбор месяца, четыре вкладки, отчёт с диаграммами."""
    st.title(TITLE)
    data = storage.load_budget()
    month = render_month_selector(data)
    block = models.ensure_month(data, month)
    catalog = categories.load_categories()

    plan_tab, fact_tab, report_tab, cats_tab = st.tabs(
        ["План", "Факт", "Отчёт", "Категории"])

    with plan_tab:
        render_plan_money_row(data, month, block)
        st.divider()
        render_quick_income(data, month, block)
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
            st.info("Ни плана, ни факта по группам — столбчатая диаграмма не построена.")
        if charts.ACTUAL_EXPENSES_FILE in built:
            st.image(str(charts.ACTUAL_EXPENSES_FILE))
        else:
            st.info("Фактических расходов за месяц нет — круговая диаграмма не построена.")

    with cats_tab:
        render_categories_tab(data)


render_page()
