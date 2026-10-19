from dataclasses import replace

import checkpoint_ordinary_tm as cp
import checkpoint_reusable_tm as reusable
import history_zipper_ordinary_tm as hz
from registered_table_linker import (
    ComponentSpec,
    LinkedConfiguration,
    LinkedInterpreter,
    RegisteredTableLinker,
)
from symbolic_tm import SymbolicConfiguration
from unary_counter_ordinary_tm import (
    ERROR as COUNTER_ERROR,
    READY as COUNTER_READY,
    command_state as counter_command_state,
    initial_configuration as counter_initial,
    machine as counter_machine,
    value as counter_value,
)


def _component_snapshot(linker, config, name):
    layout = linker.layout(name)
    tapes = [
        dict(config.tapes[layout.tape_start + i])
        for i in range(layout.tape_count)
    ]
    heads = tuple(
        config.heads[layout.tape_start + i]
        for i in range(layout.tape_count)
    )
    state_symbol = config.tapes[layout.register_tape][0]
    state = layout.decode_symbol(state_symbol)
    return state, tapes, heads


def test_linker_calls_history_without_state_product():
    hm = hz.machine()
    spec = ComponentSpec(
        "hist", hm,
        frozenset(hm.halting_states - {hz.ERROR_STATE}),
        frozenset((hz.ERROR_STATE,)),
    )
    linker = RegisteredTableLinker((spec,))
    start, after = "START", "AFTER"
    call = linker.call_rows(
        caller_state=start,
        component="hist",
        continuation=after,
        entry_transform=lambda q: hz.as_command_state(q, "APPEND1"),
    )
    rows = call + linker.all_service_rows()

    direct = hz.initial_configuration(("#",), reader=0)
    hz.run_command(direct, "APPEND1")
    original = hz.initial_configuration(("#",), reader=0)
    tapes, heads = linker.initial_tapes_and_heads({"hist": original})
    linked = LinkedConfiguration(start, tapes, heads)
    interp = LinkedInterpreter(linker, rows)
    while linked.state != after:
        interp.step(linked)
    state, actual_tapes, actual_heads = _component_snapshot(linker, linked, "hist")
    assert state == direct.state
    assert actual_tapes == direct.tapes
    assert actual_heads == tuple(direct.heads)


def test_linker_calls_counter_and_preserves_other_component():
    cm = counter_machine()
    specs = (
        ComponentSpec("a", cm, frozenset((COUNTER_READY,)), frozenset((COUNTER_ERROR,))),
        ComponentSpec("b", cm, frozenset((COUNTER_READY,)), frozenset((COUNTER_ERROR,))),
    )
    linker = RegisteredTableLinker(specs)
    rows = []
    rows += linker.call_rows(
        caller_state="INC_A", component="a", continuation="INC_B",
        entry_transform=lambda _: counter_command_state("INC"),
    )
    rows += linker.call_rows(
        caller_state="INC_B", component="b", continuation="DONE",
        entry_transform=lambda _: counter_command_state("INC"),
    )
    rows += linker.all_service_rows()
    ca, cb = counter_initial(2), counter_initial(5)
    tapes, heads = linker.initial_tapes_and_heads({"a": ca, "b": cb})
    config = LinkedConfiguration("INC_A", tapes, heads)
    interp = LinkedInterpreter(linker, rows)
    while config.state != "DONE":
        interp.step(config)
    _, ta, ha = _component_snapshot(linker, config, "a")
    _, tb, hb = _component_snapshot(linker, config, "b")
    assert counter_value(SymbolicConfiguration(COUNTER_READY, ta, list(ha))) == 3
    assert counter_value(SymbolicConfiguration(COUNTER_READY, tb, list(hb))) == 6


def test_linker_can_service_reusable_checkpoint_rows_on_a_finite_path():
    # Build only the finite row slice reached during 200 direct steps.  The
    # linker is row-local, so this exercises the same embedding as the full
    # 766k-row component without materializing it in the unit test.
    from symbolic_tm import SymbolicAction, SymbolicMultitapeMachine, SymbolicRow
    from flat_tm import Shift

    direct = reusable.initial_configuration("0110")
    states = []
    sparse_rows = []
    for _ in range(200):
        if direct.state not in states:
            states.append(direct.state)
        scanned = direct.scanned()
        matches = [r for r in reusable.outgoing_rows(direct.state) if r.matches(scanned)]
        assert matches
        sparse_rows.append(matches[0])
        reusable.step(direct)
    if direct.state not in states:
        states.append(direct.state)

    rows = []
    seen = set()
    for row in sparse_rows:
        key = (row.state, row.reads, row.action)
        if key in seen:
            continue
        seen.add(key)
        reads = [None] * reusable.TAPE_COUNT
        writes = [None] * reusable.TAPE_COUNT
        moves = [Shift.STAY] * reusable.TAPE_COUNT
        for tape, atom in row.reads:
            reads[tape] = atom
        for tape, value in row.action.writes:
            writes[tape] = value
        for tape, move in row.action.moves:
            moves[tape] = Shift(move)
        rows.append(SymbolicRow(
            row.state, tuple(reads),
            SymbolicAction(row.action.next_state, tuple(writes), tuple(moves)),
        ))
    machine = SymbolicMultitapeMachine(
        reusable.tape_alphabets(), cp.BLANK, tuple(states),
        frozenset((direct.state,)), tuple(rows),
    )
    spec = ComponentSpec("cp", machine, frozenset((direct.state,)))
    linker = RegisteredTableLinker((spec,))
    initial = reusable.initial_configuration("0110")
    call = linker.call_rows(
        caller_state="START", component="cp", continuation="DONE",
        entry_transform=lambda q: q,
        allowed_states=(initial.state,),
    )
    all_rows = call + linker.all_service_rows()
    tapes, heads = linker.initial_tapes_and_heads({"cp": initial})
    linked = LinkedConfiguration("START", tapes, heads)
    interp = LinkedInterpreter(linker, all_rows)
    while linked.state != "DONE":
        interp.step(linked)
    state, actual_tapes, actual_heads = _component_snapshot(linker, linked, "cp")
    assert state == direct.state
    assert actual_tapes == direct.tapes
    assert actual_heads == tuple(direct.heads)
