from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from examples.realtime_stack_tm import build_machine
from realtime_mtm import compile_realtime_mtm_to_peg


def expected(text: str) -> bool:
    for n in range(1, len(text) + 1):
        if text == "0" * n + "1" * (n + 1):
            return True
    return False


def test_machine_and_compiled_peg() -> None:
    machine = build_machine()
    grammar = compile_realtime_mtm_to_peg(machine)
    for length in range(9):
        for bits in itertools.product("01", repeat=length):
            text = "".join(bits)
            assert machine.run(text) == expected(text), text
            assert grammar.recognize(text[::-1]) == expected(text), text
