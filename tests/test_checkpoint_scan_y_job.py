from itertools import product

from checkpoint_scan_job import CheckpointCandidateScanJob
from checkpoint_scan_y_job import CheckpointCandidateYJob
from lemma32_t1 import lemma32_t1_same_gaps


def bits(n):
    for values in product("01", repeat=n):
        yield "".join(values)


def reference(word, c):
    job = CheckpointCandidateScanJob(word, c)
    while not job.done:
        job.tick()
    return job.candidate


def test_y_job_matches_indexed_checkpoint_scan_exhaustively():
    for c in (6, 7, 16):
        for n in range(1, 11):
            for word in bits(n):
                job = CheckpointCandidateYJob(word, c)
                assert job.run() == reference(word, c), (word, c)


def test_y_job_least_gap_matches_lemma32():
    for n in range(1, 11):
        for word in bits(n):
            job = CheckpointCandidateYJob(word, 16)
            job.run()
            assert job.least_gap == min(lemma32_t1_same_gaps(word)), word


def test_y_job_has_linear_empirical_step_bound():
    samples = [
        "0" * 500,
        ("01" * 250),
        ("0110" * 125),
        ("001011" * 84)[:500],
    ]
    for word in samples:
        job = CheckpointCandidateYJob(word, 16)
        job.run()
        # Deliberately loose audit bound.  Algorithm Y plus three border walks
        # is linear; this catches accidental restart/quadratic regressions.
        assert job.ticks <= 500 * len(word) + 1000, (len(word), job.ticks)
