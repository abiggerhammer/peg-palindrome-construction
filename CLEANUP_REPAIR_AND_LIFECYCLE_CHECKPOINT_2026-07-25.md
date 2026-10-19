# Producer-paid cleanup repair and lifecycle checkpoint

Date: 2026-07-25

## Executive result

The reusable checkpoint cleanup defect is repaired.

The component now distinguishes:

- `RESULT_READY`: output is available and remains intact;
- clean `READY`: all variable cleanup for that output has completed.

The producer explicitly retires a consumed result.  Retirement clears axes and
prepared patterns, restores source-terminal positions, and creates fresh
Algorithm-Y work epochs before clean `READY` is entered.  The next request then
enters the one-shot checkpoint body in exactly one local transition, regardless
of the preceding epoch length.

A compositional affine lifecycle bound has been proved for the repaired code.
For frozen source length `n >= 1`:

- one-shot local body: `E(n) <= 1130n + 612`;
- retirement after an actual E-step body: `R(n,E) <= 24E + 40n + 225`;
- clean local lifecycle: `<= 28290n + 15526`;
- registered execute-and-retire lifecycle: `<= 56580n + 31054`;
- RECOVER source construction, checkpoint, result consumption, retirement, and
  K recomputation, excluding case-specific pre-alignment:
  `<= 57964n + 31474`.

These are deliberately loose upper bounds, not fitted observations.

## Construction changes

1. Added explicit `RETIRE` control and separate result-ready/clean-ready states.
2. Moved all reset work from the beginning of the next request to retirement of
   the completed request.
3. Changed every output-consuming case path to retire only after its output
   axes have been scanned.
4. Changed case 5 to budget cleanup as part of the paused background lifecycle.
5. Changed case 6 to finish/retire any stale background result before launching
   fresh recovery.
6. Made source builders install the one-shot source-head entry positions; this
   work belongs to the new request's source-construction term.
7. Exported both ready-state IDs in the reusable checkpoint table and taught
   the registered linker/interpreter to distinguish them.
8. Added exact graph-theoretic history command bounds.
9. Made the retracted scheduler constant fail closed rather than silently
   returning 161759.

## Clean READY invariant

At clean `READY`:

- all six axes contain only their origin marker and scan it;
- all nine prepared-pattern tapes contain only the retained sentinel and scan
  the blank immediately to its right;
- both forward source heads scan END and the reverse source head scans the
  source sentinel;
- each S/T/U work tape scans virgin blank immediately to the right of a fresh
  epoch marker;
- each stack/counter work tape scans a fresh bottom marker or its prescribed
  initial top above that marker.

The next REQUEST consumes one transition and enters the original one-shot
`INITIAL` state.

## Generated artifacts

Reusable checkpoint table:

- states: 484699
- sparse rows: 766209
- result-ready state ID: 99227
- clean-ready state ID: 461838
- table SHA-256:
  `0496d1245da39b543f8d6ed3c4073a410e6229f5e1e2cc7b11b49467b8eea0e4`

Regenerated corrected source inventory:

- global tapes: 224
- global states: 1562426
- service rows: 3469035
- dispatcher rows: 35541
- constant-case rows: 7615
- remaining-case rows: 3245590
- controller rows: 3288746
- total rows: 6757781
- continuations: 125477
- highest controller state used: 125971 < 262144
- highest tape used: 223 < 224

The remaining-case row increase is mechanical: explicit cleanup continuations
and the two distinct checkpoint terminal states are now represented rather
than hidden in the next request.

## Regression results

- repaired component/dependent checkpoint suite: 25 passed;
- broader controller/worker suite: 19 passed;
- complete non-scheduler suite: 142 passed;
- focused lifecycle/history-bound suite after the proof additions: 6 passed;
- scheduler-quarantine checks: 2 passed;
- all five corrected six-case generated paths pass, including the repeated
  `3 -> 1 -> 2 -> 1 -> 4 -> 5 -> 6` sequence, bounded local case 3, and paused
  case 5 resumed/retired by case 6.

The scheduler tests were deliberately excluded because their old numerical
premise is retracted.

## Status ledger

### Proved

- output lifetime and producer-paid cleanup protocol;
- clean READY representation and constant-time local restart;
- exact 103-transition Algorithm-Y source-step bound;
- exact history command maxima RIGHT=55, LEFT=9, APPEND=49, RESET=2;
- affine one-shot, retirement, registered lifecycle, and RECOVER bounds stated
  above;
- generated source state/tape ranges remain inside their reservations.

### Computationally tested

- clean READY representation and lifecycle bounds on every binary word through
  length 6;
- longer all-zero, alternating, and mixed families through length 144;
- complete non-scheduler regression suite;
- all corrected six-case generated execution paths.

### Retracted / quarantined

- 2048 as a complete reusable lifecycle coefficient.  It remains a valid loose
  bound only for the one-shot local body.
- source scheduler constant 161759;
- generated Galil scheduler and scheduler-inclusive machine counts.

### Subsequent status

`BackgroundUnitBound`, the conditional `BackgroundCatchUp` timing theorem, and
`Case6TwoJobBound` are now proved in
`BACKGROUND_AND_CASE6_PROOF_2026-07-25.md`.  The remaining quantitative task is
to combine cases 1--6 into one source-machine predictability inequality and a
replacement Galil scheduler constant.  Semantic `CheckpointCorrect` remains a
separate named dependency.
