"""Read a source extract off disk.

One rule shapes this module: **everything is read as text**.

    pl.read_csv(path, infer_schema_length=0)

Letting Polars infer types here would be faster to write and wrong to rely on.
An untrusted extract is exactly where inference goes quiet: it would decide
``qty`` is a string because nine percent of the values carry whitespace, decide
``discount_pct`` is a float because the empty ones look like nulls, and hand back
a frame that has already made several judgement calls nobody recorded.

Reading text defers every one of those decisions to ``clean.py``, where each is
made deliberately and counted. That is the difference between a pipeline that
works and a pipeline that can say why it works.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import polars as pl

from app.pipeline.results import LoadResult

# backend/app/pipeline/load.py -> backend/app/pipeline -> backend/app -> backend/app/data
DATA_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class LoadOutput:
    """The frame, and what reading it cost.

    The pair travels together because every caller wants both: the runner
    narrates ``stats`` and the next step consumes ``frame``. Returning only the
    frame would push the caller into measuring the read itself, which is how
    timings stop being real.
    """

    frame: pl.DataFrame
    stats: LoadResult


def source_path(name: str) -> Path:
    """Resolve a dataset name to its bundled CSV.

    The name is matched against the files actually present rather than joined
    onto the directory, so nothing outside ``app/data`` is reachable through it.
    """
    for path in sorted(DATA_DIR.glob("*.csv")):
        if path.stem == name:
            return path
    raise FileNotFoundError(f"No bundled dataset named {name!r} in {DATA_DIR}")


def load_csv(name: str) -> LoadOutput:
    """Read one bundled extract, entirely as strings.

    ``parse_ms`` is measured around the read and nowhere else. Polars is fast
    enough that this is usually single digits, and reporting the real number is
    worth more than an inflated one: an engineer in the room recognises a
    plausible Polars timing.
    """
    path = source_path(name)

    started = time.perf_counter()
    frame = pl.read_csv(path, infer_schema_length=0)
    parse_ms = round((time.perf_counter() - started) * 1000)

    return LoadOutput(
        frame=frame,
        stats=LoadResult(
            name=name,
            rows=frame.height,
            columns=frame.columns,
            parse_ms=parse_ms,
        ),
    )
