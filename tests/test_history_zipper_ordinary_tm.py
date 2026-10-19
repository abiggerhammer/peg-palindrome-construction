import random

from strict_append_read_zipper import StrictAppendReadZipper
from history_zipper_ordinary_tm import (
    current_symbol,
    initial_configuration,
    machine,
    materialize,
    run_command,
)


def test_history_zipper_table_shape_and_determinism():
    m = machine()
    assert m.tape_count == 12
    assert len(m.states) > 1000
    assert len(m.rows) > len(m.states)
    m.audit_determinism()


def test_history_zipper_commands_against_strict_reference_randomized():
    rng = random.Random(0x5E1F3A5)
    data = tuple('#0101')
    reader = 2
    ref = StrictAppendReadZipper.from_cells(data, reader=reader, writer=len(data), blank='_')
    tm = initial_configuration(data, reader=reader)

    for _ in range(2500):
        choices = ['APPEND0', 'APPEND1', 'LEFT', 'RIGHT']
        command = rng.choice(choices)
        if command == 'APPEND0':
            ref.append('0')
        elif command == 'APPEND1':
            ref.append('1')
        elif command == 'LEFT':
            ref.move_left()
        else:
            ref.move_right()
        run_command(tm, command)
        assert current_symbol(tm) == ref.reader_symbol
        if _ % 17 == 0:
            assert materialize(tm) == ref.materialize()

    assert materialize(tm) == ref.materialize()


def test_history_command_graph_bounds_are_exact_and_acyclic():
    from history_zipper_ordinary_tm import maximum_microsteps_per_command

    assert maximum_microsteps_per_command() == {
        "APPEND0": 49,
        "APPEND1": 49,
        "LEFT": 9,
        "RIGHT": 55,
        "RESET": 2,
    }
