from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from realtime_mtm import MTMAction, Move, RealtimeMultitapeMachine, compile_realtime_mtm_to_peg


def build_machine() -> RealtimeMultitapeMachine:
    START, PUSH, POP, DONE, DEAD = "start", "push", "pop", "done", "dead"
    BLANK, BOTTOM, MARK = "_", "B", "Z"
    states = (START, PUSH, POP, DONE, DEAD)
    alphabet = (BLANK, BOTTOM, MARK)
    delta = {}

    def add(q, inp, read, q2, write, move):
        delta[(q, inp, (read,))] = MTMAction(q2, (write,), (move,))

    # Reachable core.
    add(START, "0", BLANK, PUSH, BOTTOM, Move.RIGHT)
    add(START, "1", BLANK, DEAD, BLANK, Move.STAY)
    add(PUSH, "0", BLANK, PUSH, MARK, Move.RIGHT)
    add(PUSH, "1", BLANK, POP, BLANK, Move.LEFT)
    add(POP, "1", MARK, POP, BLANK, Move.LEFT)
    add(POP, "1", BOTTOM, DONE, BLANK, Move.LEFT)
    add(POP, "1", BLANK, DEAD, BLANK, Move.STAY)

    # Reject malformed continuations. Fill all otherwise reachable table cells.
    for read in alphabet:
        add(POP, "0", read, DEAD, read, Move.STAY)
        add(DONE, "0", read, DEAD, read, Move.STAY)
        add(DONE, "1", read, DEAD, read, Move.STAY)
        add(DEAD, "0", read, DEAD, read, Move.STAY)
        add(DEAD, "1", read, DEAD, read, Move.STAY)

    # Defensive totalization for states whose intended invariant says read=blank.
    for q in (START, PUSH):
        for read in (BOTTOM, MARK):
            for inp in "01":
                add(q, inp, read, DEAD, read, Move.STAY)

    return RealtimeMultitapeMachine(
        input_alphabet=("0", "1"),
        tape_alphabet=alphabet,
        blank=BLANK,
        states=states,
        initial_state=START,
        accepting_states=frozenset({DONE}),
        tape_count=1,
        delta=delta,
    )


if __name__ == "__main__":
    grammar = compile_realtime_mtm_to_peg(build_machine())
    out = ROOT / "generated_1nplus1_0n.peg"
    out.write_text(grammar.to_text(), encoding="utf-8")
    print(f"wrote {out}")
