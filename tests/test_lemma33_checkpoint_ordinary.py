from lemma33_checkpoint_ordinary import PersistentLemma33CheckpointOrdinary
from lemma33_t1 import lemma33_t1_discovered_gap


def test_persistent_ordinary_selected_prefixes():
    samples = [
        "00000000000000000",
        "0110" * 8,
        "01000100101101001010",
        "001011001011001011",
    ]
    for word in samples:
        machine = PersistentLemma33CheckpointOrdinary(work_budget=200000, audit=True)
        outputs = [machine.feed(ch).output_gap for ch in word]
        expected = [lemma33_t1_discovered_gap(word[:i], 16) for i in range(1, len(word) + 1)]
        assert outputs == expected
        assert machine.launches <= len(word)


def test_search_is_retained_across_input_symbols():
    # A deliberately tiny budget makes the first ordinary checkpoint span many
    # feed calls.  The state and microstep count must advance rather than reset.
    machine = PersistentLemma33CheckpointOrdinary(work_budget=7, audit=False)
    records = [machine.feed(ch) for ch in "01000100101101001010"]
    search_records = [r for r in records if r.phase_before.name == "SEARCH"]
    assert search_records
    assert any(r.ordinary_steps == 7 for r in search_records)
    assert machine.launches < len(records)
