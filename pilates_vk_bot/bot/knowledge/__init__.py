"""Локальная база знаний Академии (Markdown) и поиск по ней."""

from .loader import KnowledgeBase, KnowledgeDoc
from .retriever import Fragment, KeywordRetriever

__all__ = ["Fragment", "KnowledgeBase", "KnowledgeDoc", "KeywordRetriever"]