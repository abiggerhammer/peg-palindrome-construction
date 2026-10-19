# Case-5 background and case-6 two-job bounds

Date: 2026-07-25

This note completes the quantitative obligations left after producer-paid
checkpoint cleanup.  It is deliberately separate from semantic correctness of
the Lemma-3.3 checkpoint.  Every theorem below says explicitly whether it is
unconditional or conditional on that semantic result.

## 1. Representation repair found during the proof

The previous case-5 success path decoded a candidate gap `d` in the background
but moved the retained `B'` and two `LEFT'` heads by `d` only when the target
prefix arrived.  That installation cost was `O(d)` and was not charged to any
background clock.  Therefore the previous claim that target-prefix handling was
constant-time was false.

The generated source now does the following.

1. During `BUILD_CANDIDATE`, each decoded candidate unit:
   - adds 16 to `TARGET`;
   - moves the retained lag two cells left;
   - moves `B'` right once and the two `LEFT'` readers right once each;
   - increments `GAP`.
2. A successful target installs `SECOND=KNOWN`, zeroes `K`, and changes finite
   control only.  It no longer contains an installation loop.
3. A rejected candidate enters `RETURN_CANDIDATE`; one clocked logical unit
   moves those three retained readers left and decrements `GAP`.
4. Case 6 may interrupt either build or return because `GAP` is exactly the
   remaining stale-head displacement.
5. Even the timing-error path in which a target has already been passed retires
   the checkpoint and then returns the prepositioned readers; it does not leave
   a latent representation error.

This repair is part of the proved bounds below.  The old unbudgeted installation
path is retracted.

## 2. Exact component costs

A registered component command with `m` local transitions costs exactly
`2m+3` primitive global transitions.  The graph-theoretic command maxima are:

| command | local | registered |
|---|---:|---:|
| history `APPEND0`/`APPEND1` | 49 | 101 |
| history `LEFT` | 9 | 21 |
| history `RIGHT` | 55 | 113 |
| unary `FRESH_ZERO` | 2 | 7 |
| unary `INC` | 2 | 7 |
| unary `DEC` | 1 | 5 |

A relation-aware right move costs at most one branch plus a history `RIGHT`,
hence at most 114.  A relation-aware left move costs at most one registered
history `LEFT`, hence at most 21.

These maxima are exact finite-graph results, not sampled running times.

## 3. BackgroundUnitBound

A *logical background unit* starts at `C5_WORK`, executes one retained worker
micro-operation, and reaches the common continuation `C5_WORK_DEC`.  Inspecting
all generated route families gives:

| route | primitive transitions through `C5_WORK_DEC` |
|---|---:|
| append one copied symbol to all three histories | 306 |
| advance the copy cursor and record its return distance | 124 |
| return one stale `B'` unit | 69 |
| return one background cursor unit | 27 |
| launch/synchronization history move | 115 |
| result-counter operation | 9 |
| build one candidate unit and preposition retained heads | **506** |
| return one rejected candidate unit | 70 |
| one catch-up comparison unit | 236 |

The maximum body is therefore 506 transitions.  At a factored-clock boundary,
`C5_WORK_DEC` performs one registered unary decrement and one branch, costing
at most six more transitions.  At a non-boundary radix digit it costs one.
Consequently, uniformly over every logical background route,

    BackgroundUnitBound = 506 + 6 = 512

primitive transitions.

This is an unconditional theorem about the generated ordinary transition
families.  It does not depend on whether the checkpoint's candidate is
semantically correct.

## 4. Per-input case-5 primitive bound

The largest path outside the background clock is the successful `FOLLOW` path.
Its exact component sum is 549 transitions; the generator retains the round
bound 560.

The proved logical budget is represented by a factored clock:

    outer = 1865
    radix = 1866
    effective units = 1865 * 1866 = 3,480,090.

Building the outer unary factor costs

    7 + 1865*7 + 1 = 13,063

primitive transitions.  Thus every case-5 input symbol costs at most

    560 + 13,063 + 3,480,090*512
      = 1,781,819,703

primitive transitions.  Reaching `FOLLOW` can only reduce this cost because
`FOLLOW` deliberately consumes the new input and does not also spend a clock in
the same input iteration.

Hence case 5 is a primitive real-time source program with the explicit
per-input constant `1,781,819,703`, conditional only on entering a valid case-5
representation.

## 5. Logical lifecycle of one frozen checkpoint

Let `n>=1` be the frozen source length.  The previously proved clean reusable
lifecycle bound is

    local_lifecycle(n) <= 28,290 n + 15,526

local checkpoint transitions, including request, execution, result state, and
producer-paid retirement.

The retained case-5 work outside that reusable lifecycle has the following
monotone-traversal bounds:

| group | logical units |
|---|---:|
| move three source heads to their ends, append the delta, synchronize `CURRENT` and `LAG`, rewind the two forward sources, position reverse source, request | `<=9n+15` |
| rewind/decode the candidate axis and source axis, construct unary candidate | `<=4n+5` |
| build/restore candidate, scan to target, catch up all currently available symbols, and return a failed candidate | `<=7n+12` |

For the last line, a checkpoint candidate satisfies
`(c-1)d <= n < cd`; the ledger uses only the weaker bounds `d<=n` and
`cd<=2n` at `c=16`.  Waiting in `FOLLOW` for a future symbol consumes no
background unit before that symbol exists, so reaching `FOLLOW` is earlier than
this complete available-work bound.

Therefore one complete retained cycle is bounded by

    (28,290n+15,526) + (20n+32)
      = 28,310n+15,558
      <= 28,400n+16,000.

Define

    F(n) = 28,400n + 16,000.

## 6. Exact clock sufficiency

For `c>5`, the checkpoint window used in the Seiferas-Galil/Lemma-3.3 schedule
is

    epsilon = (sqrt(c/(c-1)) - 1)/2,
    h(n) = max(1, floor(epsilon n)).

The implementation computes `h(n)` by exact integer square-root arithmetic;
no floating-point comparison is used in the proof certificate.

For every `n>=1`,

    n < 2h(n)/epsilon.

Proof: if `epsilon n<1`, then `h=1` and `n<1/epsilon<2/epsilon`.  Otherwise
`x=epsilon n>=1` and `floor(x)>=x/2`, so `h>=epsilon n/2`.

It therefore suffices to choose

    W >= 2*28,400/epsilon + 16,000.

Rationalizing gives

    2L/epsilon = 4L (sqrt(c(c-1)) + c-1).

For `c=16`, the exact integer-square-root ceiling is

    W_required = 3,479,884.

The generated factored clock supplies

    W_effective = 3,480,090 >= W_required.

For every `n>=1`, therefore,

    W_effective h(n)
      >= 28,400n + 16,000
      = F(n).

Thus every retained frozen job can perform all work that is available through
checkpoint completion, result decoding, candidate preparation, cleanup, and
catch-up to the live input within its checkpoint window.  If it reaches
`FOLLOW`, each later symbol is checked by the separately bounded constant-time
input path.

## 7. Initial case-5 catch-up and the SG runway

Let

    A = RIGHT(u) - B(u) >= 1

when case 5 begins after the second candidate is discarded.  Lazy COPY/RETURN
bootstrap uses at most

    G(A) = 4A + 8

logical units: two copy units, one stale-second return unit, one background
return unit per active symbol, plus eight endpoints.

Because `W_effective>=12`, bootstrap finishes in at most `A` further input
symbols.  During that time `B` is fixed, so the first frozen source has length
at most `2A`.

Let `h` be its checkpoint window.  If `h=1`, bootstrap plus catch-up is at most
`A+1<=2A`.  If `h>1`, then

    h <= epsilon(2A),

so the total delay is at most

    (1+2epsilon)A = sqrt(16/15) A.

Exactly,

    sqrt(16/15) < 11/5

because `16/15 < 121/25`.  The `h=1` case also satisfies
`A+1 <= 11A/5` for every `A>=1`.

The SG case-5 argument gives more than

    ((c-5)/5)A = 11A/5

input symbols before the closeness invariant could be violated.  Hence the
implementation completes bootstrap and catches its first frozen job to the live
input strictly before that possible violation.

### Status of BackgroundCatchUp

The timing conclusion above is proved.  Turning the emitted candidate into the
mathematical second midpoint still depends on the semantic theorem:

> `CheckpointCorrect`: the ordinary reusable checkpoint and its retained
> result/catch-up controller implement the specialized Lemma-3.3 recognizer.

Conditional on `CheckpointCorrect` (or directly on the published Lemma-3.3
recognizer plus a refinement proof), the generated case-5 background preserves
the SG closeness invariant and emits the correct second midpoint in time.
Finite differential tests support `CheckpointCorrect`; they are not its proof.

## 8. Case6TwoJobBound

Let case 6 process `ua`, and write

    j = B(ua) - B(u) >= 1,
    A = RIGHT(u) - B(u).

Because the second midpoint was unknown, its true old gap `d*` satisfies

    d* > A/16.

When the old first midpoint fails, the new first midpoint is at or to the right
of the old second midpoint, so `j>=d*`.  Therefore

    A < 16j.

The fresh RECOVER source after appending `a` has integer length
`n=A+1`, hence

    n <= 16j.

### Stale retained-head return

There are two possible stale-head representations.

1. Heads left from the case-4 discard lie before the new first midpoint, so
   their distance is below `j`.
2. A checkpoint candidate may already have been prepositioned.  If its frozen
   length is `m`, its gap `d` satisfies `15d<=m`; moreover `m<=A`.  Thus

       d <= A/15 < 16j/15 < 2j.

The uniform return bound is therefore two jump lengths.  One stale-head unit
costs 69 transitions, contributing at most `138j`.

The background cursor moved at most the active source length and costs 27 per
returned unit, contributing at most `27n`.  Relation copies and finite dispatch
are bounded by ten transitions.

An outstanding checkpoint has frozen length at most `n`.  Completing it from
an arbitrary active/result/cleanup state and retiring it is no more expensive
than the complete registered lifecycle

    56,580n + 31,054.

The subsequent fresh RECOVER job, including source construction, checkpoint,
result scans, retirement, and `K` recomputation, costs at most

    57,964n + 31,474.

Consequently

    case6(j)
      <= 138j + 27n + 10
         + (56,580n+31,054)
         + (57,964n+31,474)

and, using `n<=16j`,

    case6(j) <= 1,833,274j + 62,538.

Since `j>=1`,

    case6(j) <= 1,895,812j.

This is the required outstanding-plus-fresh two-job bound.  It is unconditional
as a transition-cost theorem and conditional on the established SG cursor
representation when interpreted as a source predictability statement.

## 9. Validation

### Mechanically checked

- exact component command graph maxima;
- every listed background route and the 506-transition maximum;
- exact integer computation of the required clock budget and checkpoint window;
- `W_effective*h(n)>=F(n)` for all `1<=n<=100,000`;
- initial runway inequality for all `1<=A<=100,000`;
- case-6 affine inequality for all `1<=j<=10,000`;
- no generated `INSTALL_LOOP` remains;
- candidate preposition and incremental return states are present;
- all five direct remaining-case regression tests, including repeated
  `3,1,2,1,4,5,6` and paused case-5/case-6 resumption;
- regenerated source manifest is byte-identical across independent runs.

The finite ranges test the implementation.  The proofs are the graph and
algebraic arguments above.

## 10. Regenerated source inventory

The corrected transition families were regenerated twice from source and the
manifests were byte-identical (`SHA-256 da0be2a2948b568c7a5b4d024ae642bbf55d48b20338fdfa46a78f6d2115b0d8`).
The unscheduled source inventory is:

| item | count |
|---|---:|
| global tapes | 225 |
| global states before continuation allocation | 1,562,426 |
| service rows | 3,346,002 |
| dispatcher rows | 35,541 |
| constant-case rows | 7,615 |
| remaining-case rows | 3,113,014 |
| controller rows | 3,156,170 |
| **total rows** | **6,502,172** |
| registered continuations | 2,444 |
| maximum controller state used | 2,935 of 262,144 reserved |
| maximum tape used | 224 of 225 |

The Galil scheduler is not included.

## 11. Status ledger

### Proved

- constant-time successful case-5 installation after incremental preposition;
- rejected-candidate incremental return;
- `BackgroundUnitBound = 512` primitive transitions;
- case-5 primitive per-input bound `1,781,819,703`;
- exact factored-clock sufficiency for every nonempty frozen length;
- initial case-5 catch-up before the SG runway;
- case-6 two-job coefficient `1,895,812`.

### Proof conditional on a named semantic lemma

- case-5 preservation and correct emission of `B'`, conditional on
  `CheckpointCorrect` / the specialized Lemma-3.3 refinement.

### Computationally tested

- the finite regression and arithmetic ranges listed above;
- controller/source generation after the repair.

### Retracted

- the former `O(d)` target-time installation path;
- `124,895` logical units as a sufficient producer-paid background budget;
- scheduler constant `161,759`.

### Still required before scheduler release

- put cases 1--4 into the same primitive predictability accounting;
- combine all six cases into one explicit
  `need(u,a) <= C*avail(u,a)+D` theorem;
- regenerate and retest the Galil scheduler using that global constant;
- independently discharge `CheckpointCorrect` before treating the entire
  palindrome construction as proved.