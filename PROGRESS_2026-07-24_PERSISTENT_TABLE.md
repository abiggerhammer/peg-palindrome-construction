# Persistent ordinary-checkpoint milestone

## Reusable checkpoint epochs

`checkpoint_reusable_tm.py` wraps the one-shot 63-tape checkpoint machine with
one launch tape and an explicit finite reset microprogram.

Successive frozen words are required to be monotone extensions, exactly as in
the retained Lemma 3.3 process.  The reset path:

- clears all six candidate axes through the previous `E` end marker;
- erases and rewinds the nine prepared-pattern tapes;
- repositions all three source-terminal heads;
- starts fresh `#` epochs for the three Algorithm-Y unary work tapes per run;
- starts fresh bottom-marker epochs for all thirty stack tapes and six counters;
- reinstalls the four fixed initial stack values; and
- re-enters the unchanged one-shot checkpoint initial state.

No old stack or counter region is traversed or cleared.  The resulting table has
64 ordinary one-head tapes, 484,701 reachable states, and 766,211 sparse
one-cell rows.

## Persistent SEARCH/CATCH_UP/FOLLOW composition

`lemma33_checkpoint_ordinary.py` drives the reusable table one literal row per
SEARCH tick and uses the existing 576-entry finite phase table for all phase
changes.  A frozen checkpoint survives across input arrivals and is never
restarted at an intermediate prefix.

The current audit executor still supplies the live input history as a terminal:
it bulk-updates the three checkpoint source terminals only at a launch and
performs the CATCH_UP/FOLLOW symbol comparisons.  The already developed strict
append/read zipper is the remaining lowering for that terminal.

## SG integration

`sg_zero_ratio_machine.py` accepts `background_scan_backend="ordinary_checkpoint"`.
Thus the six-case SG loop can run its retained case-5 background using the
reusable ordinary checkpoint rows.  RECOVER and LOCAL remain separately
factored Algorithm-Y tape jobs pending the final worker-table product.
