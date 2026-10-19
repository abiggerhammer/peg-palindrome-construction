# Concrete transition bounds used by the generator

The former 2048-per-symbol paragraph conflated the one-shot checkpoint body
with source construction, output consumption, reusable cleanup, and registered
call overhead.  That complete-lifecycle claim is retracted.

The current proved bounds are maintained in `checkpoint_lifecycle_bounds.py`
and justified in `CHECKPOINT_LIFECYCLE_PROOF_2026-07-25.md`.

For frozen source length `n >= 1`:

- one-shot checkpoint body:
  `E(n) <= 1130*n + 612` local checkpoint transitions;
- producer-paid retirement after an actual E-step body:
  `R(n,E) <= 24*E + 40*n + 225`;
- clean local lifecycle, including REQUEST and RETIRE:
  `<= 28290*n + 15526`;
- registered execute-and-retire lifecycle:
  `<= 56580*n + 31054` global transitions;
- RECOVER source construction, checkpoint, result scans, retirement, and K
  recomputation, excluding case-specific pre-alignment:
  `<= 57964*n + 31474` global transitions.

The exact graph-theoretic component bounds used in this accounting are:

- Algorithm-Y source step: 103 ordinary transitions;
- history RIGHT: 55 local / 113 registered transitions;
- history LEFT: 9 local / 21 registered transitions;
- unary FRESH_ZERO, INC, DEC: 7, 7, 5 registered transitions.


## Cases 1--4 primitive bounds

The complete ordinary source costs from `READ0/READ1` through source output are:

- case 1: `1433`;
- case 2: `<=264841*j`;
- case 3: `<=891977*j` uniformly over its at-end, large-gap, and small-gap branches;
- case 4: `1468`;

where `j=B(ua)-B(u)`.  The sharper affine subcase bounds and the specialized
case-3 `4j`-window proof are in
`CASES_1_4_PREDICTABILITY_PROOF_2026-07-25.md`.  For the even-palindrome
completion language, `avail(u,a)=2j-1` exactly.

## Case-5 background bounds

The generated case-5 worker now uses a factored fixed clock.  For `c=16`:

- required logical background units per input: `3,479,884`;
- generated clock shape: `1865 * 1866 = 3,480,090` units;
- maximum primitive cost of one logical unit: `512` transitions;
- clock construction: at most `13,063` transitions;
- complete case-5 primitive work per input: at most
  `1,781,819,703` transitions.

The retained checkpoint-cycle bound is

    F(n) <= 28400*n + 16000

logical units.  With the exact Lemma-3.3 window
`h=max(1,floor(epsilon*n))`, the factored clock satisfies

    3,480,090*h >= F(n)

for every nonempty frozen length `n`.  Initial lazy COPY/RETURN setup and the
first frozen job also complete strictly inside the SG case-5 runway.  Together
with the proved `CheckpointCorrect` theorem, this is now an unconditional
timing-and-correctness result for the retained case-5 worker.

A previously unbudgeted `O(d)` successful-candidate installation was found
during this proof.  Candidate construction now prepositions the retained
`B'`/`LEFT'` heads incrementally; successful installation is constant-time,
and rejection returns the prepositioned heads incrementally.

## Case-6 two-job bound

For jump `j=B(ua)-B(u)`, the current generated case-6 path—including stale
head returns, completion/retirement of any outstanding checkpoint, and a
fresh RECOVER checkpoint—is bounded by

    1,895,812*j

primitive transitions.

## Scheduler status

No complete source-machine predictability constant is yet certified.  All six
case-specific primitive bounds and the exact availability identity are now
proved; they must be assembled into one global
`need(u,a) <= C*avail(u,a)+D` theorem before the Galil scheduler can be
regenerated.  `construction_constants.scheduler_predictability_constant()`
therefore continues to fail closed.

## Global source predictability and Galil translation

The six proved case bounds combine to

    need(u,a) <= 947906*avail(u,a) + 1782767609.

Let `e(x)` be the shortest extension length taking `x` into the even-palindrome
language and set `k(x)=max(e(x)-1,0)`.  This is an output-predicting function in
Galil's sense, and

    Delta k(x,a) >= avail(x,a)-1 >= -1.

A direct case-by-case translation gives the smaller certified Galil constant

    c_G = 1781819703,

rather than the generic affine-only choice `max(C,D)=1782767609`.  Galil's
fast/slow scheduler therefore advances the physical input head every

    2*c_G = 3563639406

source-machine primitive steps while in slow mode.

The literal `(mode,clock)` expansion would contain `4*c_G=7127278812` states
and `12*c_G=21381836436` rows.  It is retired.  The replacement stores an exact
32-bit countdown on fixed one-cell tapes.  Its 63 disjoint sparse rows perform
one decrement per source step and reload the period when the value one is
reached.  This compact scheduler specification is proved and regenerated in
`generated/galil_scheduler_c16.json`; physical composition with the source and
constant speedup remain separate obligations.
