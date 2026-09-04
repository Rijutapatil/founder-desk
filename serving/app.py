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
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.answerer import Answerer, build_answerer
from agent.conversation import Conversation
from agent.retrieval.rerank import load_reranker
from agent.schema import Answer, EntityType

log = structlog.get_logger(__name__)


@dataclass
class State:
    answerer: Answerer | None = None
    corpus_size: int = 0
    error: str | None = None
    # Sessions live in memory and die with the process. That is the right
    # lifetime here: a session holds only what the founder said about their own
    # company - state, entity type - and this service is meant to run locally,
    # so persisting it would create a small store of somebody's business details
    # for no benefit they asked for.
    sessions: dict[str, Conversation] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.answerer is not None

    def conversation(self, session_id: str) -> Conversation:
        assert self.answerer is not None
        if session_id not in self.sessions:
            self.sessions[session_id] = Conversation(self.answerer)
        return self.sessions[session_id]


state = State()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build once at startup. The corpus is static between ingest runs."""
    try:
        state.answerer = build_answerer(load_reranker(os.environ.get("RERANKER", "auto")))
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


STATIC_DIR = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)


class ChatReply(BaseModel):
    answer: Answer
    known: str = Field(description="Facts carried forward, e.g. 'entity: llp · state: MH'.")
    resolved_from_pending: bool = Field(
        default=False,
        description="True when this message answered the previous clarifying question.",
    )


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    state: str | None = Field(default=None, description="ISO 3166-2:IN code, e.g. MH")
    entity: EntityType | None = None


# Cross-origin access, off unless asked for.
#
# A UI served from another origin - a Next.js app on :3000 against this on :8123
# - cannot call the API at all without this, and the browser's error says
# nothing useful about why. It is opt-in rather than open by default because
# this service is meant to run locally and answer for one person: a default of
# "*" would mean any page the user visits could quietly query their session.
#
#     FOUNDER_DESK_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
def cors_origins() -> list[str]:
    raw = os.environ.get("FOUNDER_DESK_CORS_ORIGINS", "")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


_origins = cors_origins()
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")


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


@app.post("/chat", response_model=ChatReply)
def chat(request: ChatRequest) -> ChatReply:
    """One turn of a session.

    Differs from ``/ask`` in the two ways that make a conversation work: a
    clarifying question can be answered by the next message, and facts the
    founder has stated carry forward.
    """
    if state.answerer is None:
        raise HTTPException(status_code=503, detail=state.error or "corpus not loaded")
    conversation = state.conversation(request.session_id)
    turn = conversation.ask(request.message)
    return ChatReply(
        answer=turn.answer,
        known=conversation.known,
        resolved_from_pending=turn.resolved_from_pending,
    )


@app.post("/chat/reset")
def chat_reset(session_id: str) -> dict[str, str]:
    state.sessions.pop(session_id, None)
    return {"status": "reset"}


@app.post("/ask", response_model=Answer)
def ask(request: AskRequest) -> Answer:
    if state.answerer is None:
        raise HTTPException(status_code=503, detail=state.error or "corpus not loaded")
    return state.answerer.answer(request.question, state=request.state, entity=request.entity)
