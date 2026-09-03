"""The CI gate. Its job is to make a regression impossible to merge unnoticed."""

from __future__ import annotations

from eval.gate import compare_to_baseline

BASE = {
    "n": 65,
    "cost_per_answer": 0.0,
    "retrieval": {"recall@1": 0.61, "recall@5": 0.85, "mrr": 0.71},
    "routing": {"overall": 0.86, "over_refusal": 0.12},
    "grounding": {"faithful": 1.0, "fabricated": 0.0, "unofficial": 0.0},
}


def _current(**overrides):
    current = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BASE.items()}
    for path, value in overrides.items():
        group, _, key = path.partition(".")
        if key:
            current[group][key] = value
        else:
            current[group] = value
    return current


def test_an_unchanged_run_passes() -> None:
    assert compare_to_baseline(_current(), BASE).passed


def test_noise_within_tolerance_passes() -> None:
    assert compare_to_baseline(_current(**{"retrieval.recall@5": 0.84}), BASE).passed


def test_a_real_accuracy_drop_fails() -> None:
    result = compare_to_baseline(_current(**{"retrieval.recall@5": 0.73}), BASE)
    assert not result.passed
    assert "retrieval.recall@5" in str(result)


def test_a_single_fabricated_citation_fails_the_build() -> None:
    """Zero tolerance. Citing authority the system was never shown is a bug, not a score."""
    result = compare_to_baseline(_current(**{"grounding.fabricated": 0.001}), BASE)
    assert not result.passed
    assert "fabricated" in str(result)


def test_an_unofficial_source_fails_the_build() -> None:
    assert not compare_to_baseline(_current(**{"grounding.unofficial": 0.01}), BASE).passed


def test_refusing_everything_does_not_sneak_through() -> None:
    """Without an over-refusal gate, 'I cannot answer that' would pass every other check."""
    result = compare_to_baseline(_current(**{"routing.over_refusal": 0.40}), BASE)
    assert not result.passed
    assert "over_refusal" in str(result)


def test_a_corpus_rotting_in_place_fails() -> None:
    """The quiet failure mode.

    When sources drift past their refresh windows every citation goes stale,
    but retrieval and routing do not move at all - the system is still finding
    exactly the right span, it has just stopped being able to vouch for it.
    Only faithfulness registers this, so it is gated. Verified against the real
    system by backdating the corpus: faithfulness fell to 0.753 while recall and
    routing held steady.
    """
    result = compare_to_baseline(_current(**{"grounding.faithful": 0.75}), BASE)
    assert not result.passed
    assert "grounding.faithful" in str(result)


def test_a_cost_blowout_fails() -> None:
    base = {**BASE, "cost_per_answer": 0.01}
    assert not compare_to_baseline(_current(cost_per_answer=0.05), base).passed


def test_improvements_are_reported_not_failed() -> None:
    result = compare_to_baseline(_current(**{"retrieval.recall@5": 0.95}), BASE)
    assert result.passed
    assert result.improvements


def test_a_changed_question_count_is_noted() -> None:
    result = compare_to_baseline(_current(n=80), BASE)
    assert any("question count changed" in n for n in result.notes)
