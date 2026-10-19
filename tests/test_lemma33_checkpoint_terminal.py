from itertools import product

from lemma33_checkpoint_terminal import PersistentLemma33CheckpointTerminal
from lemma33_t1 import lemma33_t1_discovered_gap


def test_terminal_background_selected_long_words():
    samples = (
        '0' * 32,
        '0110' * 8,
        '01000100101101001010010010110100',
    )
    for word in samples:
        machine = PersistentLemma33CheckpointTerminal(
            work_budget=200000, bootstrap_limit=0, audit=True
        )
        outputs = [machine.feed(symbol).output_gap for symbol in word]
        assert outputs == [
            lemma33_t1_discovered_gap(word[:index], 16)
            for index in range(1, len(word) + 1)
        ]
        assert machine.terminal.ordinary_steps > 0


def test_terminal_background_exhaustive_short():
    for length in range(1, 5):
        for bits in product('01', repeat=length):
            word = ''.join(bits)
            machine = PersistentLemma33CheckpointTerminal(
                work_budget=200000, bootstrap_limit=0, audit=True
            )
            for symbol in word:
                machine.feed(symbol)
