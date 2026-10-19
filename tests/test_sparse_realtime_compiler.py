from itertools import product

from realtime_mtm import Move
from sparse_realtime_mtm import (
    SparseRTAction,
    SparseRTRow,
    SparseRealtimeMultitapeMachine,
    compile_sparse_realtime_mtm_to_peg,
)


def build_sparse_machine():
    alphabet = ('_', 'X')
    stay = (Move.STAY,)
    return SparseRealtimeMultitapeMachine(
        input_alphabet=('0', '1'),
        tape_alphabets=(alphabet,),
        blank='_',
        states=('q0', 'q1'),
        initial_state='q0',
        accepting_states=frozenset({'q1'}),
        rows=(
            SparseRTRow('q0', '0', (None,), SparseRTAction('q0', (None,), (Move.RIGHT,))),
            SparseRTRow('q0', '1', (frozenset(alphabet),), SparseRTAction('q1', ('X',), (Move.LEFT,))),
            SparseRTRow('q1', '0', (None,), SparseRTAction('q0', (None,), (Move.LEFT,))),
            SparseRTRow('q1', '1', (None,), SparseRTAction('q1', (None,), (Move.RIGHT,))),
        ),
    )


def test_sparse_machine_compiles_without_cartesian_read_expansion():
    machine = build_sparse_machine()
    machine.audit_determinism()
    grammar = compile_sparse_realtime_mtm_to_peg(machine)
    for length in range(7):
        for bits in product('01', repeat=length):
            word = ''.join(bits)
            assert grammar.recognize(word[::-1]) == machine.run(word), word


def test_sparse_compiler_handles_distinct_tape_alphabets():
    machine = SparseRealtimeMultitapeMachine(
        input_alphabet=('0', '1'),
        tape_alphabets=(('_', 'A'), ('_', 'B', 'C')),
        blank='_',
        states=('s', 't'),
        initial_state='s',
        accepting_states=frozenset({'t'}),
        rows=(
            SparseRTRow(
                's', '0', (None, None),
                SparseRTAction('s', (None, 'B'), (Move.RIGHT, Move.LEFT)),
            ),
            SparseRTRow(
                's', '1', (None, frozenset({'_', 'B', 'C'})),
                SparseRTAction('t', ('A', None), (Move.LEFT, Move.RIGHT)),
            ),
            SparseRTRow(
                't', '0', (None, None),
                SparseRTAction('s', (None, None), (Move.STAY, Move.STAY)),
            ),
            SparseRTRow(
                't', '1', (None, None),
                SparseRTAction('t', (None, 'C'), (Move.RIGHT, Move.RIGHT)),
            ),
        ),
    )
    grammar = compile_sparse_realtime_mtm_to_peg(machine)
    for length in range(6):
        for bits in product('01', repeat=length):
            word = ''.join(bits)
            assert grammar.recognize(word[::-1]) == machine.run(word), word
