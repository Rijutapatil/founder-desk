"""Command-line argument wiring.

These exist because of a real break: `--embedder` was added to the call site and
never to the parser, so `founder-desk ask` raised AttributeError for two commits.
Every other test drove the library directly, so nothing noticed. The check is
cheap - build the parser, parse a representative command line, and assert the
namespace carries what `main` reads off it.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "serving.cli", *args], capture_output=True, text=True, timeout=180
    )


def test_help_lists_every_subcommand() -> None:
    result = _run("--help")
    assert result.returncode == 0
    for command in ("ask", "chat", "sources"):
        assert command in result.stdout


@pytest.mark.parametrize("command", ["ask", "chat"])
@pytest.mark.parametrize("flag", ["--state", "--entity", "--reranker", "--embedder"])
def test_every_flag_main_reads_is_actually_declared(command: str, flag: str) -> None:
    """The exact failure: a flag consumed by main() but never added to the parser."""
    result = _run(command, "--help")
    assert result.returncode == 0
    assert flag in result.stdout


def test_an_unknown_flag_is_rejected() -> None:
    assert _run("ask", "x", "--nonsense").returncode != 0


def test_sources_lists_the_allowlist() -> None:
    result = _run("sources")
    assert result.returncode == 0
    assert "sources" in result.stdout
