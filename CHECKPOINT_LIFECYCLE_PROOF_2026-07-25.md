# Reusable checkpoint cleanup and lifecycle proof

Date: 2026-07-25

Scope: corrected six-case SG source construction, before Galil scheduling.  This
proof replaces the retracted claim that an entire reusable checkpoint lifecycle
costs 2048 primitive transitions per frozen symbol.

## Result

The reusable checkpoint now has two distinct terminal states.

- `RESULT_READY`: the output axes are intact and may be consumed.
- `READY`: the completed request has paid for all variable cleanup.

A `RETIRE` request moves from `RESULT_READY` through cleanup to `READY`.  From
clean `READY`, a new request enters the one-shot `INITIAL` state in exactly one
local checkpoint transition.  Thus the cost of request i is no longer deferred
to request i+1.

For a nonempty frozen word of length n, let E be the actual number of one-shot
checkpoint transitions from `INITIAL` to `RESULT_READY`.  The following bounds
are proved from the generated microprograms:

    E <= 1130 n + 612
    RETIRE(n,E) <= 24 E + 40 n + 225

Consequently:

    clean READY -> result -> clean READY
        <= 28290 n + 15526 local checkpoint transitions

and the two registered source-machine calls (execute, then retire) cost at most

    56580 n + 31054 global ordinary-TM transitions.

Including the literal RECOVER source construction and result consumption, but
excluding case-specific old-cursor alignment:

    RECOVER lifecycle <= 57964 n + 31474 global transitions.

The constants are deliberately loose.  They are finite, mechanically tied to
the current source, and sufficient for subsequent case bounds.

## 1. Clean READY invariant

At clean `READY`:

1. every output/candidate axis contains only its marker at cell 0, and its head
   scans that marker;
2. every prepared-pattern tape contains only its retained sentinel at cell 0,
   and its head scans the blank cell 1;
3. `SRC_FWD` and `SRC_FWD2` scan the current END marker;
4. `SRC_REV` scans the current sentinel;
5. each Algorithm-Y S/T/U tape scans virgin blank immediately to the right of a
   new epoch marker;
6. each stack/counter tape scans a new bottom marker or its fixed initial top
   immediately above that marker.

The lifecycle regression checks this representation after every short binary
word and after several substantially different old epoch lengths.

## 2. One-shot body bound

The three frozen patterns have lengths

    n, 2n+1, 2n+1,

whose sum is `5n+2`.

For a pattern of length m:

- table construction advances the stage head at most m times;
- the later failure-chain walk moves the border head strictly left, and hence
  invokes at most m backpointer steps.

Therefore the three wrapped Algorithm-Y runs perform at most

    2(5n+2) = 10n+4

Algorithm-Y source steps.  The generated ordinary microprogram is acyclic
between source-step boundaries, and its exact graph-theoretic maximum is 103
ordinary transitions.  Its contribution is at most

    103(10n+4) = 1030n+412.

The remaining checkpoint controller has a direct tag-by-tag bound below
`70n+100`.  We retain the simpler conservative bound `100n+200`:

- source/pattern preparation and initial rewinds: at most `20n+32`;
- singleton setup, helper scans, border marking/checking, axis rewinds, and the
  final 16-to-1 ratio/merge scan: at most `32n+45`;
- the unused margin covers terminal/singleton branches independently of which
  branch is taken.

Thus

    E <= 1030n+412 + 100n+200 = 1130n+612.

## 3. Producer-paid retirement bound

The reset program is counted directly.

| Retirement part | Bound |
|---|---:|
| RETIRE dispatch | 1 |
| first rewind of six axes | `6E+6` |
| simultaneous axis clear and six final rewinds | `7n+19` |
| nine pattern rewind/clear/rewind cycles | `9E+30n+75` |
| source-head terminal positioning | `3n+6` |
| nine S/T/U fresh epochs and 36 stack/counter epochs | `9E+123` |

For the pattern term, the total prepared body length is

    3n + 3(2n+1) + 3(2n+1) = 15n+6.

For an S/T/U tape, the current epoch is contiguous and followed by virgin
blank.  During E one-shot transitions its used extent can grow by at most E,
so the reset scan is at most E plus a fixed endpoint cost.  Stack/counter heads
finish at their current top and start the next epoch by one move into virgin
blank.

Summing the table gives

    RETIRE(n,E) <= 24E + 40n + 225.

This includes the transition that consumes `RETIRE`.  No variable cleanup
remains at clean `READY`.

## 4. Registered-call lifting

For a component command with m local transitions, the registered fabric uses
exactly `2m+3` global transitions: caller/load, alternating load and active
steps, and the shared return dispatch.

The execution call costs `2E+3`.  The retirement call enters the first cleanup
state directly and therefore actually saves the local RETIRE-dispatch step;
using the full retirement bound remains a safe overestimate.  Hence

    execute + retire <= 2E+3 + 2 RETIRE(n,E)+3
                     <= 56580n+31054.

## 5. RECOVER source and result terms

The history zipper command microprograms have exact graph-theoretic maxima:

| Command | Local transitions | Registered transitions |
|---|---:|---:|
| RIGHT | 55 | 113 |
| LEFT | 9 | 21 |
| APPEND0/APPEND1 | 49 | 101 |
| RESET | 2 | 7 |

Unary `FRESH_ZERO`, `INC`, and `DEC` cost 7, 7, and 5 registered transitions.
Counting the literal `_emit_fresh_checkpoint_sources` and
`_emit_copy_active_suffix` program gives at most `161n+20` transitions.

The two result-axis scans and K recomputation are bounded by:

    OUT2 <= 369n+364
    OUT1 <= 709n+13
    recompute K <= 145n+23.

Their sum is at most `1223n+400`.  Adding source construction, registered
checkpoint execution/retirement, and result consumption yields

    RECOVER <= 57964n+31474.

## 6. Validation status

### Proved

- clean READY representation implied by every reset-program exit;
- one-transition local start from clean READY;
- exact history-command and Algorithm-Y command graph bounds;
- affine one-shot, retirement, registered lifecycle, and RECOVER bounds above.

### Computationally tested

- clean READY representation on all binary words through length 6;
- one-shot and retirement bounds on the same exhaustive set;
- longer all-zero, alternating, and mixed families through length 144;
- all six corrected SG case-body regressions after the lifecycle change.

Finite tests check the implementation; they are not the proof of the affine
bounds.

### Subsequent quantitative work

The case-5 background-unit/catch-up and case-6 two-job bounds are proved in
`BACKGROUND_AND_CASE6_PROOF_2026-07-25.md`.  A complete source-machine
predictability constant, combining all six cases, is still required before
scheduler regeneration.

The old scheduler constant remains retracted and quarantined.
