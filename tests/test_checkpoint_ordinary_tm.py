from itertools import product

from checkpoint_ordinary_tm import (
    CANDIDATE_TAPE,
    DONE,
    OUT1_TAPE,
    OUT2_TAPE,
    TAPE_COUNT,
    export_summary,
    initial_configuration,
    marker_positions,
    run,
    run_checkpoint_ordinary,
)
from checkpoint_scan_y_tape_job import CheckpointCandidateYTapeJob


def expected(word: str):
    job = CheckpointCandidateYTapeJob(word, 16)
    job.run()
    return job.gaps, job.candidate


def test_checkpoint_ordinary_shape():
    summary = export_summary()
    assert summary["tapes"] == TAPE_COUNT == 63
    assert summary["states"] == 484_522
    assert summary["sparse_rows"] == 765_979
    assert summary["operational_callbacks"] is False


def test_checkpoint_ordinary_exhaustive_binary_through_6():
    for n in range(1, 7):
        for bits in product("01", repeat=n):
            word = "".join(bits)
            actual = run_checkpoint_ordinary(word)
            gaps, candidate = expected(word)
            assert actual.gaps == gaps, word
            assert actual.candidate == candidate, word


def test_checkpoint_ordinary_candidate_boundary():
    for word in ("0" * 15, "0" * 16, "01" * 15, "0110" * 8):
        actual = run_checkpoint_ordinary(word)
        gaps, candidate = expected(word)
        assert actual.gaps == gaps
        assert actual.candidate == candidate


def test_checkpoint_output_is_on_unary_axis_tapes():
    config = initial_configuration("0000")
    run(config)
    assert config.state == DONE
    assert marker_positions(config, OUT1_TAPE) == (1,)
    assert marker_positions(config, OUT2_TAPE) == (2,)
    assert marker_positions(config, CANDIDATE_TAPE) == ()
