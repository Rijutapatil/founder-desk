"""The zero-cost baseline the CI gate runs.

Pure retrieval, no model, no key, no network: the store is built from the
committed corpus and the answerer quotes what it finds. Cost per answer is
exactly $0.0000, which is the point - a gate that costs money to run is a gate
that eventually gets switched off, so the per-commit gate is the one that is
free to run forever.

It is also a deliberately strong bar. Departmental FAQs are written in the
language people ask questions in, so "find the FAQ entry that matches" is a
genuinely good strategy. Anything added on top - a reranker, a model - has to
beat this by a margin worth its latency and spend, or it is decoration.
"""

from __future__ import annotations

from agent.answerer import Answerer, build_answerer
from agent.retrieval.rerank import IdentityReranker


def nearest_faq_baseline() -> Answerer:
    return build_answerer(IdentityReranker())


__all__ = ["Answerer", "nearest_faq_baseline"]
