"""Простой ключевой поиск по базе знаний (упрощённый RAG).

Поиск работает по отдельным фрагментам документов: запрос нормализуется,
разбивается на слова (без стоп-слов), и каждый фрагмент получает оценку
совпадений. Морфология русского языка учитывается усечённой основой слова
(первые N символов), что делает поиск устойчивым к падежам. Эмбеддинги и
векторные модели не используются — они не требуются для базы из нескольких
десятков фрагментов.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache

from .loader import CATEGORIES, KnowledgeBase

STOPWORDS = frozenset(
    """
    и в на с о а но как что для от до по из за у же ли бы не да нет есть
    быть мой ваш наш их это этот эта том тем чем при про под над без всё
    можно нельзя будет буду хотите хотите нужен нужна просто очень ещё
    the a an of to in on for and or is are was were be do does did you we
    they it that this with as at by from your me my my me please
    """.split()
)


@dataclass(frozen=True)
class Fragment:
    """Фрагмент базы знаний, найденный поиском."""

    text: str
    doc_title: str
    category: str
    source: str
    collected: str
    score: float


@dataclass
class RetrievalResult:
    """Итог поиска: фрагменты + сигнал «достаточно ли информации»."""

    fragments: list[Fragment] = field(default_factory=list)

    @property
    def best_score(self) -> float:
        return self.fragments[0].score if self.fragments else 0.0

    @property
    def context_text(self) -> str:
        """Подготовленный к передаче модели блок контекста."""

        if not self.fragments:
            return ""
        parts: list[str] = []
        for i, frag in enumerate(self.fragments, 1):
            parts.append(f"[Фрагмент {i}] ({frag.doc_title})\n{frag.text}")
        return "\n\n".join(parts)


@lru_cache(maxsize=8192)
def _stem(word: str) -> str:
    """Усечённая основа слова для сопоставления падежных форм."""

    if len(word) <= 4:
        return word
    return word[: max(4, len(word) - 2)]


@lru_cache(maxsize=8192)
def _extract_terms(text: str) -> tuple[str, ...]:
    lowered = re.sub(r"[^\w\s-]", " ", text.lower(), flags=re.UNICODE)
    return tuple(
        _stem(w)
        for w in lowered.split()
        if len(w) >= 2 and w not in STOPWORDS
    )


class KeywordRetriever:
    """Поиск релевантных фрагментов внутри разделов базы знаний."""

    def __init__(
        self,
        kb: KnowledgeBase,
        *,
        min_score: float = 0.12,
        max_fragments: int = 5,
    ) -> None:
        self.kb = kb
        self.min_score = min_score
        self.max_fragments = max_fragments

    def search(self, query: str, category: str) -> RetrievalResult:
        """Найти фрагменты по запросу в рамках категории.

        Поиск выполняется по документам указанной категории и по категории
        ``common`` (общие материалы, контакты). Если категория неизвестна,
        используется вся база — но вызов из диалогового менеджера всегда
        передаёт конкретную категорию.
        """

        if category in CATEGORIES:
            search_categories: list[str] = [category]
        else:
            search_categories = [c for c in CATEGORIES if c != "common"]
        if "common" in CATEGORIES and "common" not in search_categories:
            search_categories.append("common")

        candidates: list[Fragment] = []
        for cat in search_categories:
            for doc in self.kb.docs.get(cat, ()):
                for fragment_text in doc.fragments:
                    score = self._score(query, fragment_text)
                    if score > 0:
                        candidates.append(
                            Fragment(
                                text=fragment_text,
                                doc_title=doc.title,
                                category=doc.category,
                                source=doc.source,
                                collected=doc.collected,
                                score=score,
                            )
                        )

        candidates.sort(key=lambda f: f.score, reverse=True)
        kept = [c for c in candidates if c.score >= self.min_score][: self.max_fragments]
        return RetrievalResult(fragments=kept)

    # ------------------------------------------------------------------ #

    @staticmethod
    def _score(query: str, fragment: str) -> float:
        query_terms = set(_extract_terms(query))
        if not query_terms:
            return 0.0
        fragment_terms = _extract_terms(fragment)
        if not fragment_terms:
            return 0.0
        fragment_set = set(fragment_terms)

        overlap = len(query_terms & fragment_set)
        if overlap == 0:
            # мягкая проверка частичного совпадения (например, короткие термины)
            near = sum(
                1
                for qt in query_terms
                if any(SequenceMatcher(None, qt, ft).ratio() >= 0.82 for ft in fragment_set)
            )
            if near == 0:
                return 0.0
            overlap = 0.5 * near

        return overlap / (len(query_terms) ** 0.5)