"""Seeded randomness only. CLAUDE.md rule 8."""

import pytest

from app.core.rng import jitter, make_rng


def test_the_same_seed_gives_the_same_sequence() -> None:
    """Two runs at the same seed produce identical logs. This is why."""
    first = [make_rng(1337).random() for _ in range(3)]
    second = [make_rng(1337).random() for _ in range(3)]
    assert first == second


def test_different_seeds_diverge() -> None:
    assert make_rng(1).random() != make_rng(2).random()


def test_jitter_is_reproducible_for_a_seed() -> None:
    assert [jitter(make_rng(7), 200) for _ in range(3)] == [jitter(make_rng(7), 200)] * 3


def test_jitter_stays_inside_its_bounds() -> None:
    rng = make_rng(99)
    for _ in range(500):
        value = jitter(rng, 200)
        assert 120 <= value <= 320  # 200 * 0.6 through 200 * 1.6, rounded


def test_jitter_actually_varies() -> None:
    rng = make_rng(4)
    assert len({jitter(rng, 500) for _ in range(50)}) > 1


def test_jitter_rejects_a_negative_base() -> None:
    with pytest.raises(ValueError, match="negative"):
        jitter(make_rng(1), -1)


def test_jitter_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="lo"):
        jitter(make_rng(1), 100, lo=1.5, hi=0.5)
