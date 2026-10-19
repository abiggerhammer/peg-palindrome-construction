# Seiferas--Galil at `r=s=0`: executable specialization

This note specializes Section 7 of Seiferas and Galil, *Real-Time
Recognition of Substring Repetition and Reversal* (1977), to

```text
EPAL = { x x^R : x in Sigma* }.
```

The paper explicitly allows nonnegative parameters.  It also says in the
introduction that `r=s=t=0` gives `{ww^R}`, so the zero boundary is not an
extrapolation.

## 1. What the moving positions become

For the prefix `u` already read, write `R = |u|`.  Define

```text
S(u) = { m : u can be extended to an even palindrome of total length 2m }.
```

Under `r=s=0`, the paper's positions reduce to

```text
B3(u)  = min S(u)
B3'(u) = min (S(u) - {B3(u)})
B4(u)  = 2 B3(u)
B2(u)  = B3(u)
B1(u)  = 0
LEFT(u) = 2 B3(u) - R.
```

The acceptance test `RIGHT(u)=B4(u)` is therefore

```text
R = 2 B3(u),
```

which says exactly that the whole prefix is an even palindrome.

There is a useful direct interpretation.  A midpoint `m<R` belongs to `S(u)`
iff

```text
u[m:R] = reverse(u[2m-R:m]),
```

or, equivalently, the suffix `u[2m-R:R]` is an even palindrome.  Consequently,
if the half-lengths of the even palindromic suffixes of `u` are

```text
d0 > d1 > ... >= 0,
```

then

```text
B3(u)  = R-d0,
B3'(u) = R-d1
```

when `d1` exists, and `B3'(u)=R+1` otherwise.  Thus the theorem is maintaining
the longest and second-longest even palindromic suffixes, encoded by their
centres rather than their lengths.

## 2. Constant-time survival test

When the next symbol `a` arrives, an old midpoint `m` survives exactly when

```text
m >= R+1
```

or, if the input has entered its proposed second half,

```text
2m > R  and  a = u[2m-R-1].
```

The head at `LEFT=2m-R` makes this a one-symbol comparison.  The scan typography
around the endpoint inequality is ambiguous in OCR, but equality at the new
right boundary must be included; for example, the candidate `m=R+1` is still
valid after the prefix grows from length `R` to `R+1`.

## 3. The six cases

Appending a symbol can only remove old candidates; it cannot create a new
candidate below the previous input end.  With `B=B3(u)` and `B'=B3'(u)`, the
paper's cases become:

1. `B` and `B'` survive: both remain unchanged.
2. Both fail: the new `B` lies strictly to the right of old `B'`.
3. `B` fails and `B'` survives: old `B'` becomes new `B`.
4. `B` survives and `B'` fails: `B` remains; the new `B'` is farther right.
5. `B'` is not currently stored and `B` survives.
6. `B'` is not currently stored and `B` fails.

The invariant stores `B'` only when it is close:

```text
B'-B <= (R-B)/c.
```

Otherwise its exact location may be omitted, provided the machine knows that it
is not close.

## 4. Lemma 3.1 after specialization

Let `n` be an old valid midpoint and let `m=n+d`, with `n<m<=R`.  Put

```text
A = u[n:R].
```

The pair supplied to the paper's set `L(m,n)` becomes `(A,A)`.  Membership is
the union of two cases.

### Full two-block case: `|A| >= 2d`

Write

```text
A = x y z,  |x|=|y|=d.
```

Then `m` is valid iff

```text
y^R is a prefix of A
z   is a prefix of A.
```

Equivalently, `A` has period `2d` and its first `2d` symbols form `x x^R`.

### Partial second-block case: `d <= |A| < 2d`

Write

```text
A = x y,  |x|=d, |y|<d.
```

Then `m` is valid iff `y^R` is a suffix of the first `d` symbols of `A`.

The implementation in `sg_zero_ratio.py` transcribes these two branches
literally and exhaustively checks the equivalence in the range covered by the
lemma's one-symbol-extension hypothesis.

When `B'<=R`, Lemma 3.1 additionally says that

```text
u[B:R] has period 2(B'-B).
```

This is the period used by every subsequent Fine--Wilf argument.

## 5. Case bounds at `r=s=0`

The general coefficient

```text
1 + (r+1)/(r+1+s)
```

becomes `2`.

* In case 2, the paper obtains

  ```text
  R-B < 4(newB-B).
  ```

  Therefore a scan costing `O(R-B)` is chargeable to the jump in `B`.

* In case 3, let `d=B'-B`.  If `d>(R-B)/c`, the same full recovery is
  chargeable to the jump `newB-B=d`.  If `d` is small, only a `4d`-symbol
  window is searched for a replacement second midpoint.  If none occurs in the
  next `d` positions, Fine--Wilf gives

  ```text
  newR-newB < 4(newB'-newB),
  ```

  so `newB'` may be forgotten.

* In case 4, the analogous estimate is

  ```text
  newR-newB < 5(newB'-newB),
  ```

  so `newB'` may again be forgotten for `c>5`.

* In case 5, a background recognizer from Lemma 3.3 searches for the second
  midpoint and catches up before the closeness invariant could be violated.

## 6. Exactly what remains unlowered

The zero-ratio read loop is executable in `sg_zero_ratio_machine.py`.  The
semantic `RECOVER` and `LOCAL` operations no longer consult the direct
palindrome oracle: they enumerate candidate midpoints using the literal
`r=s=0` predicate from Lemma 3.1.  Exhaustive tests confirm that these scans
return the same candidates as the completion definition of `S(u)`.

Those scans are not yet the paper's efficient implementation.  To obtain a
real-time transition table, they must be replaced by the `t=1` instance of
Lemma 3.2, which finds all relevant parses in linear time.  Lemma 3.2 invokes:

* Fischer--Paterson's linear-time period/string-matching construction; and
* Seiferas--Galil Theorem 2, the real-time matcher with forced mismatches.

`BACKGROUND` remains the one genuinely oracle-backed branch.  It is the `t=1`
instance of Lemma 3.3, run while case 5 persists, and uses the same offline
matcher inside a real-time catch-up schedule.

The paper also relies on two external effective simulations:

* Galil's predictability-condition lemma, converting the variable-work online
  algorithm to a real-time machine; and
* Fischer--Meyer--Rosenberg's speed-preserving conversion from multihead tape
  units to ordinary one-head-per-tape multitape machines.

The next construction task is therefore to lower Lemma 3.2 at `t=1`, then use
that implementation inside Lemma 3.3.  The logical candidate-recovery behavior
is now fixed and executable; what remains is its bounded-work schedule.

## 7. Executable checks currently present

The test suite exhaustively verifies, over binary strings through the configured
bounds:

* the completion definition of `S(u)`;
* the even-palindromic-suffix characterization;
* the specialized Lemma 3.1 equivalence;
* the period conclusion for `B3'`;
* the six-case order facts;
* the specialized case-2 Fine--Wilf bound;
* the read loop and its `B3'`-known/unknown invariant;
* Lemma-3.1-based `RECOVER` and `LOCAL` scans against direct candidates; and
* acceptance iff the current prefix is an even palindrome.

These checks audit the specialization and case transcription.  They do not yet
replace the linear-time Lemma 3.2 implementation, the Lemma 3.3 background
schedule, or the cited machine simulations by primitive transitions.

## 8. Equal-input collapse of Lemmas 3.2 and 3.3

In the zero-ratio machine the two strings supplied to Lemmas 3.2 and 3.3 are
identical because `B2=B3`.  This removes a large amount of general machinery.
For the common active suffix `A` and a gap `d`:

* when `2d<=|A|`, Lemma 3.2 accepts `d` iff `2d` is a period of `A` and
  `A[:2d]` is an even palindrome;
* when `2d>|A|`, it accepts `d` iff the suffix `A[2d-|A|:]` is an even
  palindrome centred at `d`.

`lemma32_t1.py` computes every such gap in linear time on an indexed model by
intersecting a Z-array with Manacher even-palindrome radii.  Exhaustive tests
compare it with the literal two-branch definition.

For Lemma 3.3, `(A,A)` belongs to its difference language exactly when `|A|`
is divisible by `c` and `|A|/c` is the least positive Lemma-3.2 gap.  The case-5
machine now uses this predicate instead of consulting `b3_pair`; thus no branch
of the executable read loop uses the direct palindrome oracle.  The remaining
lowering problem is operational rather than semantic: compile the linear
Z/Manacher (or the equivalent Fischer--Paterson forced-mismatch) scans and
Galil scheduler into primitive multitape transitions.
