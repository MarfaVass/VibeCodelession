"""Тесты базы знаний и поиска (проверка разделов и метаданных)."""

from __future__ import annotations

import re

import pytest

from conftest import DOCUMENTS_DIR
from bot.knowledge.loader import KnowledgeBase
from bot.knowledge.retriever import KeywordRetriever


def test_source_pages_documented_in_knowledge(kb) -> None:
    """Каждый документ ссылается на страницу сайта smartbodyacademy.ru."""

    required = {"https://smartbodyacademy.ru/trener", "https://smartbodyacademy.ru/club",
                "https://smartbodyacademy.ru/foreign", "https://smartbodyacademy.ru/training",
                "https://smartbodyacademy.ru/faq", "https://smartbodyacademy.ru/about"}
    sources = {doc.source for docs in kb.docs.values() for doc in docs}
    assert required <= sources


def test_every_document_has_metadata(kb) -> None:
    for docs in kb.docs.values():
        for doc in docs:
            assert doc.title
            assert doc.category
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", doc.collected), doc.path


def test_all_four_client_categories_have_documents(kb) -> None:
    for category in ("specialist", "club", "international", "client"):
        assert kb.docs[category], f"нет документов для категории {category}"


def test_collected_dates_are_actual_collection_day(kb) -> None:
    collected = {doc.collected for docs in kb.docs.values() for doc in docs}
    # база собрана 2026-11-03; все даты должны быть в этот день
    assert collected == {"2026-11-03"}


def test_search_hits_expected_category(kb) -> None:
    retriever = KeywordRetriever(kb)

    res = retriever.search("сколько стоит обучение Matwork 1 и что входит", "specialist")
    assert res.fragments
    categories = {f.category for f in res.fragments}
    assert "specialist" in categories
    # фрагмент о ценах тренеров
    joined = " ".join(f.text.lower() for f in res.fragments)
    assert "40 000" in joined

    res2 = retriever.search("персональные тренировки и стоимость стандарт", "client")
    assert res2.fragments
    assert any("10 000" in f.text for f in res2.fragments)


def test_search_does_not_leak_other_categories(kb) -> None:
    """Поиск в категории клуба не выдает цены частных клиентов."""

    retriever = KeywordRetriever(kb)
    res = retriever.search("стоимость семинара внутри клуба", "club")
    joined = " ".join(f.text for f in res.fragments)
    assert "350 000" in joined  # клубная цена
    assert "15 000" not in joined  # цена тарифа «Премиум» из раздела частных клиентов


def test_no_results_for_unrelated_query(kb) -> None:
    retriever = KeywordRetriever(kb)
    res = retriever.search("какая погода на Марсе завтра", "club")
    assert not res.fragments
    assert res.context_text == ""


def test_no_invented_prices_in_knowledge(kb) -> None:
    """Цены в базе знаний — только подтверждённые сайтом значения."""

    allowed = {"40 000", "50 000", "35 000", "350 000", "450 000", "150 000", "10 000", "15 000"}
    price_re = re.compile(r"\b(\d[\d ]{3,})\s*(р|руб|₽)\b")
    for docs in kb.docs.values():
        for doc in docs:
            for fragment in doc.fragments:
                for match in price_re.findall(fragment.lower()):
                    normalized = re.sub(r"\s+", " ", match[0]).strip()
                    assert normalized in allowed, (doc.path.name, normalized)