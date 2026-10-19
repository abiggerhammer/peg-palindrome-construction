from itertools import product

from checkpoint_scan_job import CheckpointCandidateScanJob
from checkpoint_scan_y_tape_job import CheckpointCandidateYTapeJob
from lemma32_t1 import lemma32_t1_same_gaps


def bits(n):
    for values in product("01", repeat=n):
        yield "".join(values)


def indexed_candidate(word, c):
    job = CheckpointCandidateScanJob(word, c)
    while not job.done:
        job.tick()
    return job.candidate


def test_tape_job_matches_indexed_job_exhaustively():
    for c in (6, 7, 16):
        for n in range(1, 10):
            for word in bits(n):
                job = CheckpointCandidateYTapeJob(word, c)
                assert job.run() == indexed_candidate(word, c), (word, c)
                assert job.least_gap == min(lemma32_t1_same_gaps(word)), word


def test_candidate_heads_move_only_linearly():
    for word in ("0" * 500, "01" * 250, "0110" * 125):
        job = CheckpointCandidateYTapeJob(word, 16)
        job.run()
        assert job.candidate_moves <= 4 * len(word)
        assert job.ticks <= 600 * len(word) + 1000


def test_tape_job_retains_two_smallest_gaps():
    for n in range(1, 10):
        for word in bits(n):
            job = CheckpointCandidateYTapeJob(word, 16)
            job.run()
            expected = tuple(lemma32_t1_same_gaps(word)[:2])
            assert job.gaps == expected, (word, job.gaps, expected)
