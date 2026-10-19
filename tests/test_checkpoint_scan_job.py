from itertools import product

from checkpoint_scan_job import CheckpointCandidateScanJob
from lemma33_persistent import checkpoint_candidate_t1


def test_resumable_scan_matches_reference_exhaustively() -> None:
    for c in (6, 7, 16):
        for n in range(13):
            for bits in product("01", repeat=n):
                word = "".join(bits)
                job = CheckpointCandidateScanJob(word, c)
                assert job.run() == checkpoint_candidate_t1(word, c)


def test_scan_has_a_small_explicit_linear_tick_bound() -> None:
    # The implementation has three constant-overhead passes.  This bound is
    # deliberately loose and is checked exhaustively over all short inputs.
    for n in range(1, 14):
        for bits in product("01", repeat=n):
            job = CheckpointCandidateScanJob("".join(bits), 16)
            job.run()
            assert job.ticks <= 12 * n + 8


def test_answer_is_not_available_before_job_finishes() -> None:
    word = "01100110011"
    job = CheckpointCandidateScanJob(word, 6)
    while not job.done:
        assert job.candidate is None
        job.tick()
