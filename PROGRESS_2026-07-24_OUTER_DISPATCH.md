# Progress: registered outer dispatcher and constant cases

This stage materializes the first complete ordinary-table slice of the final
Seiferas--Galil outer machine.

## Registered service fabric

`SparseRegisteredFabric` places nine 12-tape history zippers, one 64-tape
reusable checkpoint, and twelve unary counters on disjoint ordinary tapes.
Each component's finite state is stored on a one-cell register tape.  The
global finite state set is the sum of component state sets; it never forms a
Cartesian product.

A shared continuation-dispatch state replaces one return-state family per
component.  The exported worker body contains 3,343,562 sparse one-cell rows,
1,308,476 states, and 223 tapes, with 8,192 low-numbered states reserved for
the outer microprogram.

## Literal input dispatcher

`sg_outer_dispatcher_table.py` now executes the complete front end for one
source input symbol:

1. append the bit to B, B', LEFT, LEFT', BG, and BGL;
2. update and test all six cursor groups;
3. record the pre-decrement `gap_large` signal;
4. decrement signed unary `k` one cell at a time;
5. apply the complete 16-entry SG decision table;
6. stop at one of six explicit case-entry states.

The dispatcher has 35,541 sparse rows.  It was tested from real retained
machine snapshots chosen to exercise all six cases, and selected exactly the
same case as `OrdinarySGOuterIncremental` every time.

## Reusable history epochs

The ordinary history zipper now has a `RESET` command.  It moves all twelve
stack/counter heads to fresh cells in one transition and writes twelve new
bottom markers in the next.  This replaces the remaining Python operation
which created fresh Lemma-3.3 history objects in case 4.

## Completed case bodies

Cases 1 and 4 are fully attached:

- case 1 proceeds directly to the source-output test;
- case 4 marks B' unknown, starts fresh `k` and `BG_RETURN` epochs, resets the
  three retained Lemma-3.3 histories, and enters COPY mode;
- the output submachine temporarily moves LEFT(B) one cell, tests for the
  history sentinel, restores the cursor, and reaches explicit
  `SOURCE_DONE_0` or `SOURCE_DONE_1` states.

Dirty-history tests verify that case 4 really abandons old data rather than
relying on a newly allocated host object.

## Exact remaining boundary

The remaining case bodies are 2, 3, 5, and 6.  Their algorithms are already
executable, but their checkpoint launch/copy/result-scan loops still need to be
expressed as outer program-counter rows over the registered fabric.  Once
those four entries reach `SOURCE_DONE_0/1`, the entire online source can be
wrapped as one registered component by Galil's finite scheduler and sent to
the sparse PEG compiler.
