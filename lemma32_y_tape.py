"""RECOVER and LOCAL wrappers backed by the explicit Algorithm-Y tape job."""

from __future__ import annotations

from dataclasses import dataclass

from checkpoint_scan_y_tape_job import CheckpointCandidateYTapeJob


@dataclass(frozen=True)
class GapPairResult:
    first: int
    second: int
    ticks: int
    source_steps: int
    candidate_moves: int


def recover_pair_y_tape(word: str, anchor: int) -> GapPairResult:
    active = word[anchor:]
    if not active:
        # The outer SG convention always has the automatic future position.
        return GapPairResult(len(word) + 1, len(word) + 2, 0, 0, 0)
    job = CheckpointCandidateYTapeJob(active, 16)
    job.run()
    positions = [anchor + d for d in job.gaps]
    positions.append(len(word) + 1)
    positions = sorted(set(value for value in positions if value > anchor))
    if len(positions) < 2:
        positions.append(len(word) + 2)
    return GapPairResult(
        positions[0],
        positions[1],
        job.ticks,
        job.source_steps,
        job.candidate_moves,
    )


def next_candidate_y_tape(
    word: str, anchor: int, *, stop: int | None = None
) -> tuple[int | None, int]:
    active = word[anchor:]
    if not active:
        value = len(word) + 1
        return (value if stop is None or value <= stop else None), 0
    job = CheckpointCandidateYTapeJob(active, 16)
    job.run()
    candidates = [anchor + d for d in job.gaps]
    automatic = len(word) + 1
    if stop is None or automatic <= stop:
        candidates.append(automatic)
    candidates = sorted(
        set(
            value
            for value in candidates
            if value > anchor and (stop is None or value <= stop)
        )
    )
    return (candidates[0] if candidates else None), job.ticks


def next_candidate_y_tape_local(
    word: str, anchor: int, *, radius: int
) -> tuple[int | None, int]:
    """Find the next candidate in ``(anchor, anchor+radius]``.

    In the small-gap subcase of Seiferas--Galil case 3, Lemma 2 reduces the
    query to the first ``4*radius`` symbols of the active suffix.  Running the
    explicit Algorithm-Y tape job on exactly that frozen prefix therefore
    costs ``O(radius)`` rather than rescanning the whole active suffix.
    """

    if radius <= 0:
        raise ValueError(radius)
    active = word[anchor : anchor + 4 * radius]
    if not active:
        return None, 0
    job = CheckpointCandidateYTapeJob(active, 16)
    job.run()
    candidates = sorted(
        anchor + gap for gap in job.gaps if 0 < gap <= radius
    )
    return (candidates[0] if candidates else None), job.ticks
