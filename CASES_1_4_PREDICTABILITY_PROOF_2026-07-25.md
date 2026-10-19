# Primitive predictability bounds for SG cases 1--4

Date: 2026-07-25

Scope: corrected zero-ratio Seiferas--Galil ordinary source machine, after the
`CheckpointCorrect`, producer-paid cleanup, case-5 catch-up, and case-6 two-job
proofs.  The Galil scheduler remains excluded.

## Result

Let `u` be the old input prefix, let `a` be the next bit, and write

    A = RIGHT(u) - B(u),
    d = B'(u) - B(u),
    j = B(ua) - B(u).

The bounds below count primitive transitions from the source entry state
`READ0`/`READ1` through `SOURCE_DONE_0`/`SOURCE_DONE_1`; thus they include the
common append/dispatch program and the final output test.

| case | proved primitive bound |
|---|---:|
| 1 | `1433` |
| 2 | `231925*j + 32916 <= 264841*j` |
| 3, B reaches RIGHT | `821*j + 1934 <= 2755*j` |
| 3, large old gap | `859436*j + 32541 <= 891977*j` |
| 3, small old gap | `228355*j + 32582 <= 260937*j` |
| 3, uniform | `891977*j` |
| 4 | `1468` |

Cases 2 and 3 have `j>=1`.  Cases 1 and 4 have `j=0`.

For the even-palindrome completion language, the exact availability increment
is

    avail(u,a) = 2*j - 1.

Consequently the case-specific predictability forms may be written as

    case 2: need(u,a) <= 132421*avail(u,a) + 132420,
    case 3: need(u,a) <= 445989*avail(u,a) + 445988,

while cases 1 and 4 have constant need at the only possible value
`avail(u,a)=-1`.

All constants are conservative structural bounds tied to the checked-in
microprograms.  None is fitted to finite traces.

## 1. Exact availability identity

The shortest even-palindrome completion of a prefix `u` has total length
`2B(u)`.  Therefore its shortest remaining extension has length

    e(u) = 2B(u) - RIGHT(u).

For the next symbol,

    avail(u,a)
      = e(ua)-e(u)
      = [2B(ua)-(RIGHT(u)+1)] - [2B(u)-RIGHT(u)]
      = 2j-1.

This is an equality, not an asymptotic comparison.  In cases 1 and 4, `j=0`
and one symbol of previously available slack is consumed, hence `avail=-1`.
In cases 2 and 3, `j>=1`, hence `avail>=1`.

## 2. Common primitive wrapper

The literal dispatcher has the following worst path.

* two direct READ/CAPTURE transitions;
* six registered history APPEND calls, at most `101` transitions each;
* six relation-aware cursor advances.  Each is bounded by the registered
  history-RIGHT maximum `113`; LEFT/compare and finite-only alternatives are
  smaller;
* signed `K:=K-1` and final case dispatch, at most `10` transitions.

Thus

    Dispatcher <= 2 + 6*101 + 6*113 + 10 = 1296.

The worst output path performs registered `LB.LEFT`, one inspection,
registered `LB.RIGHT`, and the final source transition:

    Output <= 21 + 1 + 113 + 1 = 136.

These two constants are included in every public bound in this document.

## 3. Reusable helper ledgers

### 3.1 Align stale second heads

Returning `B'` one gap unit toward `B` costs

* loop branch: `1`;
* `BP.LEFT`: at most `21`;
* two `LBP.LEFT` calls: at most `42`;
* `GAP.DEC`: `5`.

Including entry, endpoint, and `K_MAG.FRESH_ZERO`,

    Align(d) <= 69d + 9.

### 3.2 Promote old B' to B

One promoted unit moves `B`, `BG`, two `LB` cells, and two `BGL` cells.  A
relation-aware right move costs at most `1+113=114`.  Including loop control,
`GAP.DEC`, and `RADIUS.INC`,

    Promote(d) <= 698d + 9.

### 3.3 Signed K adjustment

For a unary source of length `x`, `_emit_signed_adjust_by_counter` with factor
`f` uses

    (3+8f)x + 5

transitions: one destructive source read, `f` signed operations of at most
`8` transitions, two source-restoration transitions per unit, and five finite
endpoints.  Hence

    KUpdate(radius r, new gap g) <= 123r + 131g + 10.

### 3.4 Bounded OUT1 scan

Copying a unary scan limit `s` costs at most `10s+11`; each inspected output
coordinate costs at most `358`; and rewinding an axis produced by a source of
length `n` costs at most `n+2`.  Thus

    ScanNext(n,s) <= 368s + n + 14,   1 <= s <= n.

### 3.5 Quota source construction

The small-gap source builder copies exactly `q` active symbols, decrements the
quota, builds the reverse source while restoring `B`, and rewinds all three
sources.  Direct counting of the literal program gives the retained safe bound

    QuotaSource(q) <= 170q + 50.

The factor-four quota itself costs

    Multiple4(d) <= 31d + 11.

## 4. Case 1

Both old candidates survive, so

    B(ua)=B(u), B'(ua)=B'(u), j=0.

The case body is one direct transition to `OUT_CHECK`.  Therefore

    need_1 <= 1296 + 1 + 136 = 1433.

This agrees with the paper's statement that case 1 has constant need.

## 5. Case 2

Both old candidates fail.  Candidate ordering gives

    new B > old B',

so `d<j`.  The specialized Fine--Wilf argument gives the strict inequality

    A < 4j.

The fresh RECOVER source includes the newly appended symbol and therefore has
length

    n=A+1 <= 4j.

The proved full RECOVER lifecycle is

    Recover(n) <= 57964n + 31474.

The literal case-2 path is dispatcher, stale-second alignment, RECOVER, one
transition to `OUT_CHECK`, and output:

    need_2
      <= 1296 + (69d+9) + (57964n+31474) + 1 + 136
      <= 231925j + 32916.

Since `j>=1`, the affine constant may be absorbed:

    need_2 <= 264841j.

The Fine--Wilf inequality is the `r=s=0` specialization of the paper's case-2
bound `RIGHT(u)-B(u)<2(1+(r+1)/(r+1+s))j`, whose coefficient becomes four.

## 6. Case 3 geometry

Old `B` fails and old `B'` survives.  Therefore

    new B = old B',
    j = d.

The implementation first runs `Promote(j)`.  Three subcases follow.

### 6.1 New B is at RIGHT

The next automatic candidate is one cell to the right.  The path advances the
new second heads by one, increments GAP, updates K with radius `j` and gap
`1`, and performs output:

    need_3,end <= 821j + 1934 <= 2755j.

### 6.2 Large old gap

The dispatch flag is the old sign of `16d-A`.  In this subcase

    16j > A.

After promotion the active checkpoint source has length

    n = A+1-j <= 15j.

The path constructs the source, executes and retires the checkpoint, scans for
the next OUT1 marker, and updates K.  The checkpoint always supplies a next
gap `g<=n`, because midpoint RIGHT is an automatic candidate.  Substitution in
the literal ledger gives

    need_3,large
      <= 821j + 57241n + 32541
      <= 859436j + 32541
      <= 891977j.

(The first displayed coefficient already includes the common dispatcher;
`821j` is promotion plus the radius part of K update.)

### 6.3 Small old gap: the 4j-window lemma

Here

    16j <= A,

so after promotion at least

    A+1-j >= 15j+1 > 4j

active symbols remain.  The generated LOCAL path therefore copies exactly the
first `4j` active symbols.

Let `b=new B`.  For every prospective next midpoint `X` with

    b < X <= b+j,

Seiferas--Galil Lemma 3.1 and the Fine--Wilf periodicity lemma give

    X is a candidate for the full active suffix
      iff
    X is accepted using the first 4j active symbols.

At `r=s=0`, the Lemma-3.1 predicate is `sg_l0_member`.  Its first branch uses
only the first `2(X-b)<=2j` symbols of the first input and the first `X-b<=j`
symbols of the second; its partial branch uses still less.  Consequently
truncating both identical checkpoint inputs to `4j` is harmless.  By
`CheckpointCorrect`, the LOCAL checkpoint marks exactly these bounded
candidates and the OUT1 scan returns the least one.

If such an `X` exists, its new gap `g` is at most `j`.  If no such `X` exists,
the paper's second Fine--Wilf argument gives

    RIGHT(ua)-new B < 4(new B'-new B).

Thus the unknown new gap is greater than one quarter of the active length and,
a fortiori, greater than one sixteenth.  Dropping the exact second heads is
therefore permitted by invariant clause (2).  This proves both terminal paths
of the generated LOCAL branch.

The found path is the more expensive one.  With `q=4j`, its literal ledger is

    Dispatcher
    + Promote(j)
    + Multiple4(j)
    + QuotaSource(4j)
    + RegisteredCheckpointLifecycle(4j)
    + ScanNext(4j,j)
    + KUpdate(j,g<=j)
    + Output,

which simplifies to

    need_3,small <= 228355j + 32582 <= 260937j.

The missing path substitutes `Align(j)` and the constant case-4 freshening tail
for K update and is strictly smaller than the retained public bound.

### 6.4 Uniform case-3 result

Taking the maximum of the three subcase coefficients,

    need_3 <= 891977j.

## 7. Case 4

Old B survives and old B' fails, so `j=0`.  The specialized case-4 Fine--Wilf
estimate is

    RIGHT(ua)-B(ua) < 5(B'(ua)-B(ua)).

Since `c=16>5`, the new second gap is too large to require exact heads.  The
implementation merely marks the second unknown, freshens K and BG_RETURN, and
starts three new history epochs.  Every fresh/reset call is constant-time:

    need_4
      <= 1296 + 1 + 2*7 + 3*7 + 136
      = 1468.

The stale physical B'/LEFT' heads are not traversed here; their later return is
charged incrementally to case 5 or explicitly to case 6, as proved in the
previous timing theorem.

## 8. Proof status and mechanical evidence

### Proved

* exact availability identity `avail=2j-1`;
* case-2 order and Fine--Wilf geometry;
* specialized case-3 4j-window equivalence and safe-forgetting inequality;
* specialized case-4 safe-forgetting inequality;
* every primitive ledger and the public coefficients above.

### Computationally tested

* the availability identity and case geometry on every binary prefix through
  length 12;
* the local predicate equivalence whenever reached in the exhaustive audit,
  plus the production small-gap example of length 66;
* literal ordinary-table executions of representatives of case 1, case 2,
  all three exercised case-3 branches, and case 4;
* the existing corrected case-body and `CheckpointCorrect` regressions.

The representative literal step counts are stored in
`generated/case14_literal_step_audit_2026-07-25.json`.  They are evidence, not
part of the proof.

### Still separate

This document does not yet combine cases 1--6 into a single pair `(C,D)` for

    need(u,a) <= C*avail(u,a)+D.

The exact availability identity and all six primitive case bounds are now
available, so that combination is the next proof step.  The Galil scheduler
remains quarantined until it is completed.