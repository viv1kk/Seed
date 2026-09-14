"""The only randomness in the project.

CLAUDE.md rule 8: one seeded ``random.Random`` instance, created here. Bare
``random.*`` and ``numpy.random`` are banned everywhere else, enforced by the
ruff ``flake8-tidy-imports`` banned-api rule in ``pyproject.toml``. This module
carries the single per-file ignore for that rule.

Two runs at the same seed must produce byte-identical logs. That property is
demonstrated in the phase 2 gate and it only holds if every draw comes from a
``Random`` handed down through ``AgentContext``.
"""

import random
from typing import Final

# Re-exported so that nothing else in the project needs to `import random` just
# to spell a type. The banned-api rule would reject that import anyway.
type Rng = random.Random

DEFAULT_SEED: Final[int] = 1337

# The timing model in docs/04-AGENT-RUNTIME.md:
#     narration_ms = sum(base_step_ms * rng.uniform(0.6, 1.6) for step in task.steps)
JITTER_LO: Final[float] = 0.6
JITTER_HI: Final[float] = 1.6


def make_rng(seed: int) -> Rng:
    """Build the run's generator. One per run, created by the run registry."""
    return random.Random(seed)


def jitter(
    rng: Rng,
    base_ms: int,
    lo: float = JITTER_LO,
    hi: float = JITTER_HI,
) -> int:
    """Scale ``base_ms`` by a seeded uniform draw.

    Keeping this here rather than calling ``rng.uniform`` inside a runner means
    the shape of the jitter is defined once and the runners stay declarative.
    """
    if base_ms < 0:
        raise ValueError("base_ms must not be negative")
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    return round(base_ms * rng.uniform(lo, hi))
