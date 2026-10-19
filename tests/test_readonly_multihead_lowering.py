from copy import deepcopy

from fp_algorithm_y_multihead import (
    C,
    D,
    MACHINE as Y_MACHINE,
    blocks_from_configuration,
    initial_configuration as y_initial,
)
from pattern_prepare_multihead import (
    MACHINE as PREP_MACHINE,
    WP,
    WPRE,
    WSUF,
    initial_configuration as prep_initial,
    output_word,
)
from readonly_multihead_lowering import (
    append_read_unit_signature,
    split_readonly_shared_tapes,
    to_flat_configuration,
    to_flat_multitape,
)


def test_prepare_readonly_source_heads_lower_to_ordinary_tapes():
    split = split_readonly_shared_tapes(PREP_MACHINE)
    assert split.remaining_shared_tapes == ()
    flat = to_flat_multitape(split.machine)

    for word in ("0", "01", "0110", "010001"):
        old = prep_initial(word)
        old_copy = old.clone()
        PREP_MACHINE.run(old_copy)

        new_mh = split.transform_configuration(PREP_MACHINE, old)
        new = to_flat_configuration(split.machine, new_mh)
        flat.run(new)

        # Writer heads retain their logical indices; after conversion, tape h
        # is the private physical tape of logical head h.
        assert output_word(old_copy, 1, old_copy.heads[WP]) == "".join(
            new.tapes[WP].get(i, "_") for i in range(new.heads[WP])
        )
        assert output_word(old_copy, 2, old_copy.heads[WPRE]) == "".join(
            new.tapes[WPRE].get(i, "_") for i in range(new.heads[WPRE])
        )
        assert output_word(old_copy, 3, old_copy.heads[WSUF]) == "".join(
            new.tapes[WSUF].get(i, "_") for i in range(new.heads[WSUF])
        )
        assert new.steps == old_copy.steps


def test_algorithm_y_pattern_heads_split_exactly():
    split = split_readonly_shared_tapes(Y_MACHINE)
    assert len(split.remaining_shared_tapes) == 1
    residual = split.remaining_shared_tapes[0]
    signature = append_read_unit_signature(split.machine, residual)
    assert signature["is_append_read_unit"]
    assert signature["reader_heads"] == (C,)
    assert signature["append_writer_heads"] == (D,)

    for pattern in ("0", "00", "0100000", "01100110", "01@10"):
        old = y_initial(pattern)
        old_copy = old.clone()
        Y_MACHINE.run(old_copy)

        new = split.transform_configuration(Y_MACHINE, old)
        split.machine.run(new)
        # Re-map the residual Delta tape back to the legacy index expected by
        # blocks_from_configuration.
        legacy_view = new.clone()
        legacy_view.tapes = [
            dict(new.tapes[split.machine.head_to_tape[0]]),
            dict(new.tapes[split.machine.head_to_tape[C]]),
            dict(new.tapes[split.machine.head_to_tape[4]]),
            dict(new.tapes[split.machine.head_to_tape[5]]),
            dict(new.tapes[split.machine.head_to_tape[6]]),
        ]
        assert blocks_from_configuration(legacy_view) == blocks_from_configuration(old_copy)
        assert new.steps == old_copy.steps
