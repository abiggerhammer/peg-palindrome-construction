# Progress: ordinary transition-table production

This update completes the first full table-production stage.

## Six-tape pattern preparation

The three-head read-only source tape is duplicated exactly.  The resulting
ordinary transducer has:

- 6 one-head tapes;
- 6 states;
- 11 sparse one-cell rows.

It writes the plain, prefix-reversal, and suffix-reversal patterns.  The table
is exported as `generated/pattern_prepare_ordinary_table.json.gz`.

## Seventeen-tape Fischer--Paterson Algorithm Y

The append/read unary-Delta unit is now lowered all the way to an ordinary
one-head-per-tape machine.

A subtle representation issue in the previous imperative model has been made
explicit: assignments such as `f1 = rp1` cannot mean copying an unbounded
stack.  The table instead uses eight fixed physical queue-stack tapes and a
finite role permutation.  Only twelve permutations are reachable.  Dropping a
stale stack is implemented by a fresh bottom-marker epoch in two ordinary TM
steps, so no unbounded clearing operation is hidden.

The generated machine has:

- 17 one-head tapes;
- 124,926 finite states;
- 198,751 sparse one-cell transition rows;
- no callbacks, host arithmetic, variable-distance moves, or whole-stack
  operations;
- an exact maximum of 103 microsteps per source Algorithm-Y transition.

The complete table is
`generated/algorithm_y_ordinary_table.json.gz` (about 1.3 MB compressed).
Its wildcard notation is defined in `TABLE_FORMAT.md`; every wildcard ranges
over a declared finite tape alphabet and can be expanded mechanically into the
conventional concrete table.

## Verification

Focused cross-layer tests report:

```text
21 passed in 24.74s
```

They include exhaustive binary patterns through length 8, separator-bearing
patterns, comparison with both the original literal multihead table and the
strict-storage reference, queue random tests, read-only duplication, and the
existing multitape-to-PEG compiler tests.

The complete historical suite was not counted as passing: its older exhaustive
front-end tests exceeded the run window.

## Remaining product construction

The next table-production boundary is the checkpoint job around these two
ordinary submachines:

1. prepare two private copies of each of the three patterns;
2. invoke the ordinary Algorithm-Y table for each pattern;
3. lower the monotone candidate-marking and result-selection heads;
4. compose that job with the retained Lemma-3.3 controller, the SG six-case
   controller, and Galil's scheduler;
5. teach the factored scaffolding compiler to consume sparse rows directly,
   avoiding a pointless Cartesian expansion of ignored tape symbols.

## Sixty-three-tape checkpoint machine

The complete off-line checkpoint scan has now been lowered to an ordinary
one-head-per-tape table.  It contains:

- a preparation pass producing three private copies of each of the plain,
  prefix-reversal, and suffix-reversal patterns;
- three independent instances of the 17-tape Algorithm-Y table;
- monotone period, full-branch, and partial-branch marker tapes;
- finite-control parity bookkeeping coupled directly to Algorithm Y's A-head
  motion;
- a unary-axis merge which records the first two distinct gaps;
- the specialized `c=16` Lemma-3.3 interval test, performed by two ordinary
  source-tape heads advancing 15 and 16 cells per candidate-axis position.

The generated machine has:

- 63 ordinary one-head tapes;
- 484,522 reachable states;
- 765,979 sparse one-cell rows;
- no callbacks, host arithmetic in transitions, variable-distance moves, or
  hidden whole-tape operations.

Its output tapes mark the first gap, second gap, and Lemma-3.3 candidate at the
corresponding unary position.  The table is exported as
`generated/checkpoint_ordinary_table.json.gz` (about 4.1 MB compressed) using
the sparse-map v2 row format documented in `TABLE_FORMAT.md`.

Differential tests compare the ordinary machine with the retained
`CheckpointCandidateYTapeJob` through every binary word of length six and at
candidate-boundary lengths 15, 16, 30, and 32.  The focused checkpoint,
Algorithm-Y, and retained-source suite reports:

```text
10 passed in 25.57s
```

## Remaining product construction

The next boundary is composition rather than checkpoint logic:

1. make checkpoint storage reusable by fresh epochs between retained scans;
2. inline the persistent Lemma-3.3 controller and catch-up/follow phases;
3. compose the SG six-case controller and Galil scheduler;
4. teach the scaffolding compiler to ingest sparse-map rows directly;
5. emit and test the final PEG.
