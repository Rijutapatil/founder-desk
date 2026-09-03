"""The HTTP surface."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from ingest.build_corpus import load_spans  # noqa: E402
from serving.app import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_does_not_depend_on_the_corpus(client) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_ready_reflects_the_corpus(client) -> None:
    response = client.get("/ready")
    if load_spans():
        assert response.status_code == 200
        assert response.json()["spans"] > 0
    else:
        assert response.status_code == 503


def test_sources_lists_the_allowlist_including_blocked(client) -> None:
    if not load_spans():
        pytest.skip("no corpus")
    body = client.get("/sources").json()
    assert body["count"] > 10
    assert any(s["fetch_status"] == "blocked" for s in body["sources"])
    assert all(s["licence"] for s in body["sources"])


def test_ask_returns_a_grounded_answer(client) -> None:
    if not load_spans():
        pytest.skip("no corpus")
    body = client.post(
        "/ask", json={"question": "can a one person company get startup india benefits"}
    ).json()
    assert body["kind"] == "grounded"
    assert body["cited_spans"]
    assert "NOT PROFESSIONAL ADVICE" in body["disclaimer"]


def test_ask_refuses_rather_than_guessing(client) -> None:
    if not load_spans():
        pytest.skip("no corpus")
    body = client.post("/ask", json={"question": "how do I train a neural network"}).json()
    assert body["kind"] == "refused"
    assert body["searched"]


def test_a_blank_question_is_rejected(client) -> None:
    assert client.post("/ask", json={"question": "x"}).status_code == 422
