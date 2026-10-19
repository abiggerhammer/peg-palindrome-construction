from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compile_sa_to_peg import compile_to_peg
from examples.anbn import build_anbn_automaton


def expected_anbn(text: str) -> bool:
    n0 = len(text) - len(text.lstrip("0"))
    return text == "0" * n0 + "1" * n0


def expected_reverse(text: str) -> bool:
    return expected_anbn(text[::-1])


def test_scaffolding_automaton_exhaustive() -> None:
    automaton = build_anbn_automaton()
    for length in range(9):
        for bits in itertools.product("01", repeat=length):
            text = "".join(bits)
            assert automaton.run(text) == expected_anbn(text), text


def test_compiled_peg_exhaustive() -> None:
    automaton = build_anbn_automaton()
    grammar = compile_to_peg(automaton)
    for length in range(9):
        for bits in itertools.product("01", repeat=length):
            text = "".join(bits)
            assert grammar.recognize(text) == expected_reverse(text), text
