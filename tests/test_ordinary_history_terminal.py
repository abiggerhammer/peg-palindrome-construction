from checkpoint_ordinary_tm import run_checkpoint_ordinary
from checkpoint_reusable_tm import result, retire_result, run_to_result
from ordinary_history_terminal import OrdinaryHistoryTerminal


def test_terminal_initializes_checkpoint_without_bulk_source_write():
    for word in ('0', '01', '0110', '0' * 15, '0' * 16):
        terminal = OrdinaryHistoryTerminal(word)
        checkpoint, _ = terminal.initialize_checkpoint()
        run_to_result(checkpoint)
        actual = result(checkpoint)
        expected = run_checkpoint_ordinary(word)
        assert actual.gaps == expected.gaps
        assert actual.candidate == expected.candidate


def test_terminal_extends_reusable_checkpoint_monotonically():
    words = ('0', '01', '0110', '01100110', '011001100110')
    terminal = OrdinaryHistoryTerminal(words[0])
    checkpoint, _ = terminal.initialize_checkpoint()
    run_to_result(checkpoint)
    retire_result(checkpoint)
    previous = words[0]
    for word in words[1:]:
        for symbol in word[len(previous):]:
            terminal.append(symbol)
        terminal.request_extended_checkpoint(checkpoint)
        run_to_result(checkpoint)
        actual = result(checkpoint)
        expected = run_checkpoint_ordinary(word)
        assert actual.gaps == expected.gaps
        assert actual.candidate == expected.candidate
        retire_result(checkpoint)
        previous = word


def test_terminal_period_comparison_cursors():
    samples = (
        ('0110', '01100110', 4),
        ('0101', '01010101', 4),
        ('0011', '00110110', 4),
        ('00000', '0000000000', 2),
    )
    for prefix, word, period in samples:
        terminal = OrdinaryHistoryTerminal(prefix)
        terminal.initialize_checkpoint()
        for symbol in word[len(prefix):]:
            terminal.append(symbol)
        terminal.prepare_comparison(period)
        actual = []
        for index in range(len(prefix), len(word)):
            match, _ = terminal.compare_next(compare=index >= period)
            actual.append(match)
        expected = [
            True if index < period else word[index] == word[index - period]
            for index in range(len(prefix), len(word))
        ]
        assert actual == expected
