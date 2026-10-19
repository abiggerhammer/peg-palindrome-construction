# Progress: rebuilt SG cases 2, 3, 5, and 6

This stage starts from the durable outer-dispatch checkpoint and restores the
four case bodies that were previously described but not saved.  The code and
tests in this archive are the durable implementation.

## Case 2: shared RECOVER

Case 2 now aligns the stale second midpoint group to the first, creates fresh
checkpoint source epochs, copies the active suffix one cell at a time, executes
the registered reusable checkpoint, scans the two unary result axes, installs
both midpoint groups, and recomputes signed unary `k`.

## Case 3: promotion and all subprograms

Case 3 promotes the surviving second midpoint while retaining the old gap in a
unary `RADIUS` counter.  Its three routes are literal table programs:

- the at-input-end one-cell successor;
- the large-gap full checkpoint search;
- the small-gap checkpoint restricted to the first `4d` symbols.

A length-66 periodic regression enters the small-gap route with
`B=33`, `B'=35`, and `k=-1`; the local scan installs `(B,B')=(35,37)` and
restores `k=0`.  The local-miss route aligns the spare heads and joins the
same retained-background initializer as case 4.

## Case 5: retained bounded work

Case 5 uses a finite `L33_PHASE` tape and a unary fixed-work clock.  It retains
COPY, RETURN, launch, checkpoint SEARCH, result scan, target construction,
CATCH_UP, and FOLLOW state across source input symbols.  One SEARCH tick
executes one row of the ordinary 64-tape checkpoint table; the checkpoint's
finite state remains in its registered state cell.

The production clock is `124895` work units per source symbol.  Tests also use
smaller clocks to expose pause/resume boundaries cheaply.

## Case 6: interruption and shared RECOVER

Case 6 finishes the stale `B'` and background-cursor returns, copies the live
relation symbols to the spare groups, resumes any paused checkpoint state to
READY, discards the old background epoch, and enters the same RECOVER body as
case 2.

## Deferred checkpoint row families

The checkpoint has hundreds of thousands of states.  The two large outer
families are streamed instead of materialized as Python row objects:

- `single_step`: one checkpoint transition, guarded by `L33_PHASE == SEARCH`;
- `run_to_ready`: registered checkpoint service used by case 6.

`LazySparseFabricInterpreter` performs the same operations on demand during
differential tests.  A regression reaches a genuine paused SEARCH in case 5
and then interrupts it through case 6.

## Corrected source-table inventory

With the production clock, the complete unscheduled source construction has:

- 224 ordinary tapes;
- 1,562,428 global states, including a 262,144-state outer-controller reserve;
- 3,469,033 registered worker-service rows;
- 1,756,301 controller rows;
- 5,225,334 sparse one-cell transition rows total.

The remaining-case stream alone contains 1,713,145 rows.  A full stream pass
verified that every row state is in the controller reserve and every tape
reference is in `[0,223]`.  The counts are recorded in
`generated/sg_source_row_manifest.json`.

A monolithic 5.2-million-row JSONL copy is intentionally not included: the
transition families themselves are the canonical generated representation,
and the attempted serialization exceeded the available single-command run
window.  No incomplete export is present in this archive.

## Regression evidence

The heavy generated machines were tested in separate processes to avoid
retaining multiple decoded checkpoint tables simultaneously:

- 4 sparse registered-linker tests;
- 1 dispatcher test covering all six cases;
- 1 case-1/case-4 test;
- case-2 differential recovery;
- case-3 at-end and full-recovery routes;
- case-3 bounded small-gap route;
- repeated ordinary execution of `0011000`, producing cases
  `3 -> 1 -> 2 -> 1 -> 4 -> 5 -> 6`;
- case-5 paused SEARCH followed by case-6 checkpoint resumption;
- 2 independent incremental-source regressions.

There is still no `palindrome.peg`.  The next boundary is Galil scheduling,
then the explicit fixed-speed representation required by the scaffolding/PEG
compiler.
