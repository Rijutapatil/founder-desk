"""HTTP service.

Two operational decisions worth stating.

*Readiness is separate from liveness.* ``/health`` says the process is up;
``/ready`` says the corpus loaded and the system can actually answer. A load
balancer that routes on the first will send traffic to a process that is running
and useless.

*There is no degraded mode.* If the corpus is missing, ``/ask`` returns 503
rather than answering from nothing. For compliance information, returning
nothing is strictly better than returning a guess, and a service that quietly
degrades is one whose worst answers are invisible.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.answerer import Answerer, build_answerer
from agent.retrieval.rerank import load_reranker
from agent.schema import Answer, EntityType

log = structlog.get_logger(__name__)


@dataclass
class State:
    answerer: Answerer | None = None
    corpus_size: int = 0
    error: str | None = None

    @property
    def ready(self) -> bool:
        return self.answerer is not None


state = State()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build once at startup. The corpus is static between ingest runs."""
    try:
        state.answerer = build_answerer(load_reranker(os.environ.get("RERANKER", "identity")))
        state.corpus_size = len(state.answerer.store)
        log.info("ready", spans=state.corpus_size)
    except (RuntimeError, ImportError) as exc:
        state.error = str(exc)
        log.error("startup_failed", error=str(exc))
    yield


app = FastAPI(
    title="founder-desk",
    description="Grounded first-year compliance answers for new Indian companies.",
    lifespan=lifespan,
)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    state: str | None = Field(default=None, description="ISO 3166-2:IN code, e.g. MH")
    entity: EntityType | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, object]:
    if not state.ready:
        raise HTTPException(status_code=503, detail=state.error or "corpus not loaded")
    return {"status": "ready", "spans": state.corpus_size}


@app.get("/sources")
def sources() -> dict[str, object]:
    """What the system is allowed to read, including what it could not collect."""
    if state.answerer is None:
        raise HTTPException(status_code=503, detail=state.error or "corpus not loaded")
    allowlist = state.answerer.allowlist
    return {
        "count": len(allowlist),
        "sources": [
            {
                "id": e.id,
                "publisher": e.publisher,
                "title": e.title,
                "url": e.url,
                "authority_tier": int(e.authority_tier),
                "licence": e.license,
                "fetch_status": e.fetch_status.value,
            }
            for e in allowlist.entries
        ],
    }


@app.post("/ask", response_model=Answer)
def ask(request: AskRequest) -> Answer:
    if state.answerer is None:
        raise HTTPException(status_code=503, detail=state.error or "corpus not loaded")
    return state.answerer.answer(request.question, state=request.state, entity=request.entity)
