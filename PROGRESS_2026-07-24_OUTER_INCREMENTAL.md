# Progress: incremental outer/result lowering

This stage removes three host-level shortcuts that remained in the retained
Lemma 3.3 / SG composition.

## Candidate marker and target arithmetic

`lemma33_checkpoint_incremental.py` no longer calls
`checkpoint_reusable_tm.result()` when a checkpoint reaches READY.

The machine now:

1. rewinds `CANDIDATE_TAPE` to `#` one cell at a time;
2. rewinds `SRC_FWD` to its sentinel;
3. advances both axes together;
4. records the current one-based position in a literal unary counter;
5. detects `G` or the source `!` directly.

For a discovered gap `d`, the candidate counter is traversed and restored while
it constructs `16d` unary target units and positions LAG by exactly `2d-1`.
The frozen source is then scanned cell by cell to subtract the checkpoint
length.  Later CATCH_UP and FOLLOW steps decrement the same target counter.
The comparison-start signal is the actual symbol under LAG (`0/1` versus
sentinel/blank), so the earlier numeric `i >= 2d` branch is gone.

Host integers retained in this module are audit/output mirrors only; they no
longer decide marker discovery, comparison start, or target arrival.

## Unary result transfer into the SG outer machine

`sg_outer_incremental.py` no longer converts the Lemma 3.3 output integer back
into a newly allocated unary counter.  It consumes the retained candidate
counter directly while installing B3', then discards the completed background
job.  Thus the operational result path is unary tape to unary tape/cursors.

## Registered component service

`registered_component_service.py` implements the pause/resume mechanism needed
for final table composition without a Cartesian state product.

A large worker state is stored as one symbol on a dedicated state-register
tape.  One worker transition is serviced by:

* `LOAD`: read the state-register symbol and enter `ACTIVE(q)`;
* `ACTIVE(q)`: execute one worker row, write `q'` to the register, and return
  to `LOAD`.

The construction is tested against both the 64-tape reusable checkpoint machine
and the 12-tape strict history zipper, pausing after every worker microstep.
This changes the final controller composition from a product of worker state
sets to a sum plus finite register alphabets.

## Verification

The following groups pass separately (kept separate to avoid retaining several
giant generated tables in one pytest process):

* 4 tests: unary counters and registered component service;
* 3 tests: incremental Lemma 3.3, including a monkeypatch forbidding the old
  host result decoder;
* 2 tests: exhaustive/selected SG outer executions;
* 5 tests: all-ordinary workers, scheduler audit, and sparse PEG compiler.

## Remaining boundary

The next table is the finite outer microcontroller that invokes the registered
history/checkpoint services and the unary-counter primitives.  Once emitted,
its real-time input-step scheduler can be wrapped by Galil's fast/slow table and
passed to the sparse scaffolding/PEG compiler.
