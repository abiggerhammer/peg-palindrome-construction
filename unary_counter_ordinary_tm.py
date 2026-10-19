"""Literal ordinary-TM service for one epoch-based unary counter.

The data tape uses ``#`` as the current epoch's bottom marker and ``1`` for
units.  The head is always at the top unit or at ``#`` when the counter is
zero.  Commands are externally installed in the component state register and
then executed through :mod:`registered_table_linker`.

Every row is one ordinary read/write/move transition.  No operation traverses
more than one cell per row.
"""

from __future__ import annotations

from dataclasses import dataclass

from flat_tm import Shift
from symbolic_tm import (
    SymbolicAction,
    SymbolicConfiguration,
    SymbolicMultitapeMachine,
    SymbolicRow,
)

BLANK = "_"
BOTTOM = "#"
ONE = "1"
ALPHABET = (BLANK, BOTTOM, ONE)

READY = "UC_READY"
ERROR = "UC_ERROR"
INC_MOVE = "UC_INC_MOVE"
INC_WRITE = "UC_INC_WRITE"
DEC = "UC_DEC"
FRESH_MOVE = "UC_FRESH_MOVE"
FRESH_WRITE = "UC_FRESH_WRITE"

COMMANDS = ("INC", "DEC", "FRESH_ZERO")


def command_state(command: str) -> str:
    return {
        "INC": INC_MOVE,
        "DEC": DEC,
        "FRESH_ZERO": FRESH_MOVE,
    }[command]


def _row(state, read, next_state, write=None, move=Shift.STAY):
    return SymbolicRow(
        state,
        (read,),
        SymbolicAction(next_state, (write,), (move,)),
    )


def machine() -> SymbolicMultitapeMachine:
    rows = (
        _row(INC_MOVE, frozenset((BOTTOM, ONE)), INC_WRITE, None, Shift.RIGHT),
        _row(INC_MOVE, BLANK, ERROR),
        _row(INC_WRITE, BLANK, READY, ONE),
        _row(INC_WRITE, frozenset((BOTTOM, ONE)), ERROR),
        _row(DEC, ONE, READY, BLANK, Shift.LEFT),
        _row(DEC, frozenset((BLANK, BOTTOM)), ERROR),
        _row(FRESH_MOVE, frozenset((BOTTOM, ONE)), FRESH_WRITE, None, Shift.RIGHT),
        _row(FRESH_MOVE, BLANK, ERROR),
        _row(FRESH_WRITE, BLANK, READY, BOTTOM),
        _row(FRESH_WRITE, frozenset((BOTTOM, ONE)), ERROR),
    )
    states = (
        READY, ERROR, INC_MOVE, INC_WRITE, DEC, FRESH_MOVE, FRESH_WRITE,
    )
    return SymbolicMultitapeMachine(
        (ALPHABET,), BLANK, states, frozenset((READY, ERROR)), rows
    )


def initial_configuration(value: int = 0) -> SymbolicConfiguration:
    if value < 0:
        raise ValueError(value)
    tape = {0: BOTTOM}
    for pos in range(1, value + 1):
        tape[pos] = ONE
    return SymbolicConfiguration(READY, [tape], [value])


def value(config: SymbolicConfiguration) -> int:
    pos = config.heads[0]
    count = 0
    while config.tapes[0].get(pos, BLANK) == ONE:
        count += 1
        pos -= 1
    if config.tapes[0].get(pos, BLANK) != BOTTOM:
        raise AssertionError((pos, config.tapes[0].get(pos, BLANK)))
    return count
