"""Lemma 3.2 RECOVER/LOCAL workers composed from ordinary transition tables.

The worker copies its finite active input through the twelve-tape ordinary
history zipper into the 64-tape checkpoint machine, executes the checkpoint
one literal row at a time, and reads the two unary gap markers.  Thus the
operational worker no longer calls the indexed failure, Z, Manacher, or
multihead Algorithm-Y implementations.

The surrounding SG executor still chooses the active substring in host code;
that cursor selection is the remaining outer-product boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from checkpoint_reusable_tm import result as checkpoint_result, run_to_result
from ordinary_history_terminal import OrdinaryHistoryTerminal


@dataclass(frozen=True)
class OrdinaryRecoverResult:
    first: int
    second: int
    ordinary_steps: int
    checkpoint_steps: int
    terminal_steps: int


@dataclass(frozen=True)
class OrdinaryLocalResult:
    candidate: int | None
    ordinary_steps: int
    checkpoint_steps: int
    terminal_steps: int
    window_length: int


def _run_checkpoint(word: str):
    if not word or any(symbol not in "01" for symbol in word):
        raise ValueError(word)
    terminal = OrdinaryHistoryTerminal(word)
    checkpoint, _ = terminal.initialize_checkpoint()
    run_to_result(checkpoint)
    return terminal, checkpoint, checkpoint_result(checkpoint)


def recover_pair_ordinary(word: str, anchor: int = 0) -> OrdinaryRecoverResult:
    if not 0 <= anchor < len(word):
        raise ValueError((anchor, len(word)))
    active = word[anchor:]
    terminal, checkpoint, result = _run_checkpoint(active)
    gaps = list(result.gaps)
    automatic = len(active) + 1
    while len(gaps) < 2:
        gaps.append(automatic)
        automatic += 1
    return OrdinaryRecoverResult(
        anchor + gaps[0],
        anchor + gaps[1],
        terminal.ordinary_steps + checkpoint.steps,
        checkpoint.steps,
        terminal.ordinary_steps,
    )


def next_candidate_ordinary_local(
    word: str,
    anchor: int,
    *,
    radius: int,
) -> OrdinaryLocalResult:
    if radius <= 0:
        raise ValueError(radius)
    if not 0 <= anchor < len(word):
        raise ValueError((anchor, len(word)))
    # The specialized proof only needs the first 4d active symbols.
    active = word[anchor : anchor + 4 * radius]
    terminal, checkpoint, result = _run_checkpoint(active)
    gap = next((candidate for candidate in result.gaps if candidate <= radius), None)
    return OrdinaryLocalResult(
        None if gap is None else anchor + gap,
        terminal.ordinary_steps + checkpoint.steps,
        checkpoint.steps,
        terminal.ordinary_steps,
        len(active),
    )
