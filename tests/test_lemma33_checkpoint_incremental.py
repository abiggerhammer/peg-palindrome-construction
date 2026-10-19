from itertools import product

from lemma33_checkpoint_incremental import IncrementalLemma33CheckpointTerminal
from lemma33_t1 import lemma33_t1_discovered_gap


def test_incremental_launch_wrapper_matches_semantics_short_words():
    for length in range(1, 6):
        for bits in product('01', repeat=length):
            word = ''.join(bits)
            machine = IncrementalLemma33CheckpointTerminal(
                work_budget=200000, audit=True
            )
            outputs = [machine.feed(ch).output_gap for ch in word]
            assert outputs == [
                lemma33_t1_discovered_gap(word[:i], 16)
                for i in range(1, len(word) + 1)
            ]


def test_incremental_launch_can_span_many_feed_calls():
    word = '01100110011001100110011001100110'
    machine = IncrementalLemma33CheckpointTerminal(work_budget=8192, audit=True)
    outputs = [machine.feed(ch).output_gap for ch in word]
    assert outputs == [lemma33_t1_discovered_gap(word[:i], 16) for i in range(1, len(word)+1)]
    assert machine.launches >= 1


def test_incremental_checkpoint_does_not_use_host_result_decoder(monkeypatch):
    import checkpoint_reusable_tm as reusable

    def forbidden(*_args, **_kwargs):
        raise AssertionError("host result decoder was called")

    monkeypatch.setattr(reusable, "result", forbidden)
    word = "0" * 16
    machine = IncrementalLemma33CheckpointTerminal(work_budget=200000, audit=True)
    outputs = [machine.feed(ch).output_gap for ch in word]
    assert outputs == [lemma33_t1_discovered_gap(word[:i], 16) for i in range(1, len(word) + 1)]
