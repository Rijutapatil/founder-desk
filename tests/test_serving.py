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


class TestChat:
    """The session endpoint. Sessions are per-process and die with it."""

    def test_a_clarifying_question_can_be_answered_over_two_calls(self, client) -> None:
        if not load_spans():
            pytest.skip("no corpus")
        session = {"session_id": "test-clarify"}
        first = client.post(
            "/chat", json={**session, "message": "do I need shops and establishment registration"}
        ).json()
        assert first["answer"]["kind"] == "clarify"

        second = client.post("/chat", json={**session, "message": "Maharashtra"}).json()
        assert second["resolved_from_pending"] is True
        assert "state: MH" in second["known"]

    def test_sessions_do_not_leak_into_each_other(self, client) -> None:
        if not load_spans():
            pytest.skip("no corpus")
        client.post(
            "/chat", json={"session_id": "a", "message": "do I need GST registration in Karnataka"}
        )
        other = client.post(
            "/chat", json={"session_id": "b", "message": "can an OPC get startup india benefits"}
        ).json()
        assert "KA" not in other["known"]

    def test_reset_clears_a_session(self, client) -> None:
        if not load_spans():
            pytest.skip("no corpus")
        client.post(
            "/chat", json={"session_id": "c", "message": "do I need GST registration in Karnataka"}
        )
        client.post("/chat/reset", params={"session_id": "c"})
        after = client.post(
            "/chat", json={"session_id": "c", "message": "can an OPC get startup india benefits"}
        ).json()
        assert "KA" not in after["known"]

    def test_the_page_is_served(self, client) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "founder-desk" in response.text


class TestCors:
    """Cross-origin access: off by default, exact origins when asked for.

    A UI on another origin cannot call this at all without it, and the browser's
    console error does not explain why - so it is worth pinning both that it
    works when configured and that it stays shut when not.
    """

    def test_no_cors_headers_without_configuration(self, monkeypatch) -> None:
        from serving.app import cors_origins

        monkeypatch.delenv("FOUNDER_DESK_CORS_ORIGINS", raising=False)
        assert cors_origins() == []

    def test_origins_are_parsed_from_the_environment(self, monkeypatch) -> None:
        from serving.app import cors_origins

        monkeypatch.setenv(
            "FOUNDER_DESK_CORS_ORIGINS", "http://localhost:3000, http://127.0.0.1:3000 "
        )
        assert cors_origins() == ["http://localhost:3000", "http://127.0.0.1:3000"]

    def test_a_blank_setting_is_not_a_wildcard(self, monkeypatch) -> None:
        """The failure that would matter: an empty value read as "allow everything"."""
        from serving.app import cors_origins

        monkeypatch.setenv("FOUNDER_DESK_CORS_ORIGINS", "  , ,")
        assert cors_origins() == []
