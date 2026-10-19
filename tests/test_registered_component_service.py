from flat_tm import Shift

import checkpoint_ordinary_tm as cp
import checkpoint_reusable_tm as reusable
import history_zipper_ordinary_tm as hz
from registered_component_service import LOAD, RETURN, RegisteredComponentService


def _cp_normalize(row):
    reads = [None] * reusable.TAPE_COUNT
    writes = [None] * reusable.TAPE_COUNT
    moves = [Shift.STAY] * reusable.TAPE_COUNT
    for tape, atom in row.reads:
        reads[tape] = atom
    for tape, value in row.action.writes:
        writes[tape] = value
    for tape, value in row.action.moves:
        moves[tape] = Shift(value)
    return tuple(reads), row.action.next_state, tuple(writes), tuple(moves)


def _symbolic_normalize(row):
    return row.reads, row.action.next_state, row.action.writes, row.action.moves


def _component_snapshot(config, count):
    return (
        [dict(t) for t in config.tapes[:count]],
        tuple(config.heads[:count]),
    )


def test_registered_checkpoint_service_matches_direct_steps():
    direct = reusable.initial_configuration("01100110")
    service = RegisteredComponentService(
        tape_alphabets=reusable.tape_alphabets(),
        blank=cp.BLANK,
        outgoing=reusable.outgoing_rows,
        normalize_row=_cp_normalize,
        ready_states=(reusable.RESULT_READY, reusable.READY),
    )
    wrapped = service.wrap_configuration(
        component_state=direct.state,
        tapes=direct.tapes,
        heads=direct.heads,
    )

    for _ in range(250):
        reusable.step(direct)
        service.service_one_component_step(wrapped)
        assert wrapped.state == LOAD
        assert service.component_state(wrapped) == direct.state
        assert _component_snapshot(wrapped, reusable.TAPE_COUNT) == (
            [dict(t) for t in direct.tapes], tuple(direct.heads)
        )


def test_registered_history_service_can_pause_every_microstep():
    machine = hz.machine()
    direct = hz.initial_configuration(("#",), reader=0)
    service = RegisteredComponentService(
        tape_alphabets=machine.tape_alphabets,
        blank=machine.blank,
        outgoing=lambda state: machine._by_state.get(state, ()),
        normalize_row=_symbolic_normalize,
        ready_states=machine.halting_states - {hz.ERROR_STATE},
    )
    wrapped = service.wrap_configuration(
        component_state=direct.state,
        tapes=direct.tapes,
        heads=direct.heads,
    )

    for command in ("APPEND0", "APPEND1", "LEFT", "RIGHT", "APPEND1"):
        # The surrounding finite controller writes the command-entry state to
        # the register in one ordinary transition.
        direct.state = hz.as_command_state(direct.state, command)
        wrapped.tapes[service.register_tape][0] = hz.as_command_state(
            service.component_state(wrapped), command
        )
        while direct.state not in machine.halting_states:
            machine.step(direct)
            service.service_one_component_step(wrapped)
            assert service.component_state(wrapped) == direct.state
            assert _component_snapshot(wrapped, hz.TAPE_COUNT) == (
                [dict(t) for t in direct.tapes], tuple(direct.heads)
            )
        service.step(wrapped)  # LOAD(ready) -> RETURN
        assert wrapped.state == RETURN
        wrapped.state = LOAD
