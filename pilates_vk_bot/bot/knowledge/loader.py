"""Загрузчик локальной базы знаний.

База знаний хранится в Markdown-файлах с YAML-подобной шапкой:

    ---
    title: <тема документа>
    category: specialist | club | international | client | common
    source: <URL исходной страницы>
    collected: <дата сбора информации>
    ---
    <текст>

Документ при загрузке разбивается на абзацы-фрагменты, к которым
прикрепляются метаданные источника. Категория ``common`` — материалы,
релевантные всем категориям клиентов (общая информация, контакты).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import load_settings

CATEGORIES = ("specialist", "club", "international", "client", "common")

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass(frozen=True)
class KnowledgeDoc:
    """Один документ базы знаний."""

    path: Path
    title: str
    category: str
    source: str
    collected: str
    fragments: tuple[str, ...]


class KnowledgeBase:
    """Все документы базы знаний, сгруппированные по категориям."""

    def __init__(self, root: Path | None = None) -> None:
        settings = load_settings()
        self.root = Path(root) if root else settings.knowledge_path
        docs = self._load_all(self.root)
        self.docs: dict[str, list[KnowledgeDoc]] = {cat: [] for cat in CATEGORIES}
        for doc in docs:
            if doc.category not in self.docs:
                raise ValueError(
                    f"{doc.path.name}: неизвестная категория '{doc.category}' "
                    f"(допустимо: {', '.join(CATEGORIES)})"
                )
            self.docs[doc.category].append(doc)

    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_file(path: Path) -> KnowledgeDoc:
        """Прочитать один файл базы знаний с проверкой метаданных."""

        raw = path.read_text(encoding="utf-8").strip()
        match = _FRONTMATTER_RE.match(raw)
        if match is None:
            raise ValueError(f"{path.name}: отсутствует шапка метаданных (---...---)")

        meta: dict[str, str] = {}
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip().lower()] = value.strip()

        missing = [k for k in ("title", "category", "source", "collected") if not meta.get(k)]
        if missing:
            raise ValueError(f"{path.name}: в шапке не заполнено: {', '.join(missing)}")

        body = raw[match.end() :].strip()
        fragments = tuple(p.strip() for p in re.split(r"\n\s*\n", body) if p.strip())
        if not fragments:
            raise ValueError(f"{path.name}: документ не содержит текста")

        return KnowledgeDoc(
            path=path,
            title=meta["title"],
            category=meta["category"].lower(),
            source=meta["source"],
            collected=meta["collected"],
            fragments=fragments,
        )

    def _load_all(self, root: Path) -> list[KnowledgeDoc]:
        if not root.exists():
            raise FileNotFoundError(f"База знаний не найдена: {root}")
        docs = [self.parse_file(p) for p in sorted(root.rglob("*.md"))]
        if not docs:
            raise ValueError(f"База знаний пуста: {root}")
        return docs

    def categories(self) -> dict[str, int]:
        """Число документов по категориям (для диагностики и тестов)."""

        return {cat: len(items) for cat, items in self.docs.items() if items}

    def __len__(self) -> int:
        return sum(len(items) for items in self.docs.values())