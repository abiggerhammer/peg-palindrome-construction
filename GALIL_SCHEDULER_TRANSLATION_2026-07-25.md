# Translation to Galil's predictability condition and scheduler parameters

Date: 2026-07-25

Scope: translation of the proved corrected source-machine bounds to the exact
two-part condition in Galil, *String Matching in Real Time*, Section 2, and
regeneration of a compact fast/slow scheduler specification.

## 1. Galil's hypotheses

For an on-line source algorithm `A`, Galil writes:

- `y(x)` for the output string produced after input `x`;
- `t(x)` for cumulative source time;
- `Delta t(x,a)=t(xa)-t(x)`;
- `k(x)` for an output-predicting function: every extension of length `k(x)`
  produces only zero outputs after `y(x)`.

The required condition is that an integer `c>0` exists such that

    (G1) Delta t(x,a) > c  =>  y(xa)=y(x)0,
    (G2) Delta k(x,a) >= Delta t(x,a)/c - 2.

The fast/slow scheduler simulates the source for `2c` steps before each
speculative physical read.

## 2. Output-predicting function for the palindrome language

Let

    e(x) = min {|v| : xv is an even palindrome}.

Every binary word has such an extension.  Define

    k(x) = max(e(x)-1, 0).

### Lemma 2.1: k is output-predicting

If `e(x)<=1`, then `k(x)=0` and the claim is vacuous.  If `e(x)>=2`, no
extension of length at most `e(x)-1` can reach an accepted prefix by minimality
of `e(x)`.  Thus every one of the next `k(x)` outputs is zero.

### Lemma 2.2: one-step lower bounds

Writing

    avail(x,a)=e(xa)-e(x),

we have `avail(x,a)>=-1`, because any completion of `xa` gives a completion of
`x` one symbol longer.  Since

    max(r-1,0) >= r-1
    max(r-1,0) <= r,

we also have

    Delta k(x,a) >= avail(x,a)-1 >= -1.                 (2)

For the corrected source, `avail=2j-1` exactly.

## 3. Generic affine translation

The explicit source theorem is

    Delta t <= C*avail + D,
    C=947906,
    D=1782767609.

Using only this affine theorem and (2), `c=max(C,D)=D` satisfies Galil's two
conditions.  This already proves existence of a computable scheduler constant.

The certified case partition permits a slightly smaller value.

## 4. Direct certified constant

The current primitive bounds are:

| case | `j` | source work bound |
|---|---:|---:|
| 1 | 0 | `1433` |
| 2 | >=1 | `264841*j` |
| 3 | >=1 | `891977*j` |
| 4 | 0 | `1468` |
| 5 | 0 | `1781819703` |
| 6 | >=1 | `1895812*j` |

Define

    c_G = 1781819703.                                  (3)

This is the smallest constant certified directly by these upper bounds:
case 5 has `avail=-1`, so the generic lower bound `Delta k>=-1` requires its
entire primitive step bound to fit inside `c_G`.

### Proof of (G1)

In cases 1, 4, and 5, source work is at most `c_G`, so the antecedent is false.
In cases 2, 3, and 6, `j>=1`, hence `avail=2j-1>=1`.  If `xa` were accepted,
then `e(xa)=0`, which would imply `avail=-e(x)<=0`, a contradiction.  Therefore
any step taking more than `c_G` outputs zero.

### Proof of (G2)

For cases 1, 4, and 5, (2) gives `Delta k>=-1`, while

    Delta t/c_G - 2 <= -1.

For cases 2, 3, and 6, (2) gives

    Delta k >= 2j-2.

Their coefficients all satisfy

    264841 <= 2c_G,
    891977 <= 2c_G,
    1895812 <= 2c_G.

Therefore

    Delta t/c_G - 2 <= 2j-2 <= Delta k.

Thus (G1) and (G2) hold with (3).

## 5. Scheduler parameters

Galil's source-step clock period is

    L = 2c_G = 3563639406.                              (4)

A literal `(mode,clock)` expansion would require

    4c_G  = 7127278812 controller states,
    12c_G = 21381836436 controller rows.

That representation is mathematically finite but not a responsible artifact.
The former small unrolled `c=16` JSON is therefore retired.

## 6. Compact exact countdown

The replacement scheduler stores the remaining source-step count in binary on
32 fixed one-cell tapes, little-endian.  The period is

    L = 0xD468D26E
      = 11010100011010001101001001101110_2.

The sparse decrement table contains exactly

    2*32-1 = 63

rows:

1. one exact-value-one row emits a clock tick and reloads `L`;
2. 31 rows handle even values, partitioned by their least significant one;
3. 31 rows handle odd values greater than one, partitioned by their first
   higher one so they remain disjoint from the exact-one row.

Each positive 32-bit value matches exactly one row.  A non-tick row computes
`n -> n-1`; the tick row computes `1 -> L`.  Because the bits occupy distinct
fixed tapes, all changed bits are written in one ordinary multitape transition.
Consequently the clock emits a tick after exactly `L` source-step decrements
without an `O(L)` finite-control expansion.

The high-level FAST/SLOW rules are unchanged from Galil's construction.  An
independent compact executor agrees with the reference scheduler and the
literal unrolled controller on exhaustive small constants and traces.

## 7. What is and is not complete

Proved and regenerated:

- the six-case affine theorem;
- Galil's output-predicting function;
- both exact Galil conditions;
- `c_G=1781819703`;
- period `L=3563639406`;
- the exact 32-bit/63-row compact countdown;
- the abstract compact FAST/SLOW scheduler specification.

Still separate:

- ordinary transition-table composition of the compact scheduler with the
  6,502,172-row source;
- proof that this composition simulates the abstract scheduler;
- fixed constant speedup to the one-work-step-per-input interface expected by
  the current scaffolding-to-PEG compiler.