# Proof of `CheckpointCorrect`

Date: 2026-07-25  
Commit base: `7fd2d8dc98ddf4f2432693a7a0804420fe873616`  
Scope: the corrected, unscheduled, `c=16`, `r=s=0` Seiferas--Galil source construction.

## Status and theorem

This document discharges the semantic obligation previously called
`CheckpointCorrect`.  The proof is independent of the finite differential
regressions.  The regressions listed at the end are validation of the proof's
correspondence with the checked-in source, not a replacement for the argument.

For a nonempty binary word `w`, put `n=|w|` and define `G(w)` to be the set of
positive specialized Lemma-3.2 gaps:

- if `2d <= n`, then `d in G(w)` iff `2d` is a period of `w` and `w[0:2d]` is
  an even palindrome;
- if `n < 2d`, then `d in G(w)` iff the suffix `w[2d-n:n]` is an even
  palindrome centred at `d`.

The empty suffix makes `n in G(w)` for every nonempty `w`.

### `CheckpointCorrect`

For every nonempty binary word `w`:

1. the one-shot ordinary checkpoint machine halts in `CHECKPOINT_DONE` and its
   two output axes contain the two least distinct elements of `G(w)`, or all of
   `G(w)` when it has fewer than two elements;
2. its candidate axis contains a marker at `d` exactly when

       d = min G(w)  and  15d <= |w| < 16d;

3. the reusable checkpoint, launched from clean `READY` on any monotone source
   extension, is observationally equivalent to a fresh one-shot execution on
   that extension; `RESULT_READY` preserves the result, and `RETIRE` restores
   clean `READY` without changing the result already consumed;
4. pausing and resuming a checkpoint execution changes neither its result nor
   the source it denotes;
5. the retained Lemma-3.3 terminal emits gap `d` at a prefix `u` exactly when

       |u| = 16d  and  d = min G(u);

6. `RECOVER` returns the first two specialized candidates after its anchor,
   adding the automatic future candidates when the finite frozen word supplies
   fewer than two; `LOCAL` returns the least checkpoint candidate in the
   explicitly supplied `4r` query window whose gap is at most `r`.

Item 6 deliberately states the bounded-query meaning of `LOCAL`.  The separate
Seiferas--Galil local-window lemma is what later identifies that bounded query
with the full active suffix in small-gap case 3.  It is not smuggled into the
checkpoint theorem.

## 1. Mathematical characterization of the gaps

Let `P(i)` be the endpoint of the longest proper border of the prefix ending at
`i`, with `P(i)=-1` when no positive border exists.  Iterating

    i <- P(i)

from the final position enumerates every positive proper border length, in
strictly decreasing order, as `i+1`.

Three elementary equivalences give a failure-chain description of `G(w)`.

### Lemma 1.1 — periods

For `1 <= p <= n`, `p` is a period of `w` iff `n-p` is a border length of `w`.

**Proof.** The period equation is

    w[p:n] = w[0:n-p],

which is exactly equality of the suffix and prefix of length `n-p`.  The case
`p=n` corresponds to the empty border and is included separately.  QED.

### Lemma 1.2 — palindromic prefixes

For `1 <= l <= n`, `w[0:l]` is a palindrome iff `l` is a border length of

    w @ reverse(w),

where `@` is a separator outside the binary alphabet.

**Proof.** The prefix of length `l` of the combined word is `w[0:l]`.  Its
suffix of length `l` is `reverse(w[0:l])`.  They are equal exactly when the
prefix is a palindrome.  The separator prevents a border longer than `n` from
being confused with one of these tests.  QED.

### Lemma 1.3 — palindromic suffixes

For `1 <= l <= n`, `w[n-l:n]` is a palindrome iff `l` is a border length of

    reverse(w) @ w.

The proof is the same: the prefix of length `l` is the reverse of the suffix of
`w`, and the suffix of length `l` is the suffix itself.  QED.

### Corollary 1.4 — failure-chain gap formula

Let `Per`, `Pre`, and `Suf` be the period lengths, palindromic-prefix lengths,
and palindromic-suffix lengths supplied by Lemmas 1.1--1.3.  Then

    G(w)
      = {n}
        union { l/2 : l is even and l in Per intersect Pre }
        union { n-l/2 : l is even, l<n, and l in Suf }.

**Proof.** In the full branch put `l=2d`.  Its two defining predicates are
exactly `l in Per` and `l in Pre`.  In the partial branch the tested suffix has
length `2(n-d)`; put `l=2(n-d)`, so `d=n-l/2`.  The empty suffix is `d=n`.
QED.

This is the specification implemented independently in
`checkpoint_correctness.gap_set_from_borders`.

## 2. Correctness of Fischer--Paterson Algorithm Y

The checkpoint obtains the three failure chains through Algorithm Y.  This
section proves the source algorithm before considering its ordinary-tape
lowering.

For a pattern `x[0:m]`, define

    Delta(i) = 1 + P(i) - P(i+1),    -1 <= i < m-1,

with `P(-1)=-1`.  Algorithm Y stores the blocks

    0 1^Delta(-1) 0 1^Delta(0) 0 ...

and maintains heads representing the current prospective border endpoint `p`
and the unary jump

    lambda(p) = p-P(p) = sum_{j=-1}^{p-1} Delta(j).

### Lemma 2.1 — source-stage invariant

Immediately before computing `P(i)`, for every `i>=1`:

1. the pattern heads scan `x[P(i-1)]` (or the sentinel for `-1`) and `x[i-1]`;
2. the completed Delta blocks are exactly `Delta(-1),...,Delta(i-2)`;
3. the Delta reader and unary counters represent `P(i-1)` and
   `lambda(P(i-1))`.

### Lemma 2.2 — one source stage appends the correct block

Assuming Lemma 2.1, the stage computes `P(i)` and appends exactly
`Delta(i-1)` unary ones followed by a zero.

**Proof.** Algorithm Y first compares `x[p+1]` with `x[i]`.

- On a match, `P(i)=p+1`.  Hence

      Delta(i-1) = 1+p-(p+1) = 0,

  and the `ADV` branch appends only the zero delimiter while advancing the
  represented border.

- On a mismatch with `p>=0`, the `BACK` primitive replaces `p` by `P(p)`.
  The number of unary boundaries crossed is

      p-P(p) = lambda(p),

  and the machine appends that many ones while moving the pattern head to the
  next prospective border.  Repeating this is the ordinary KMP failure walk.

- When the walk reaches `p=-1`, the sentinel branch appends the final one and
  then the delimiter.

If the visited prospective endpoints are

    p0=P(i-1), p1=P(p0), ..., pk,

then every failure-link traversal appends `p_j-p_{j+1}` ones.  If the
comparison succeeds at `pk`, then `P(i)=pk+1`, so the traversals append

    p0-pk = 1+P(i-1)-P(i).

If the failure walk reaches `-1` and the comparison with the first pattern
symbol also fails, the traversals append `p0+1` ones and the sentinel branch
appends one more, again giving

    p0+2 = 1+P(i-1)-(-1).

Thus in both cases the total is `Delta(i-1)`.

To see maximality, every border of `x[0:i]` whose final symbol could match
`x[i]` is either the extension of the longest border of `x[0:i-1]` or the
extension of one of that border's own borders.  These are exactly the
endpoints on the failure chain, in decreasing order.  Algorithm Y stops at the
first successful extension, hence at the longest one; reaching the sentinel
means none exists.  QED.

### Theorem 2.3 — Algorithm Y failure table

The initial block is `Delta(-1)=1`.  Lemma 2.2 preserves Lemma 2.1 and advances
`i`; induction therefore proves that, at halt, every stored block is the exact
Delta block and following the encoded backpointers enumerates precisely the
failure chain of the pattern.  QED.

## 3. Correctness of the ordinary one-head lowering

The source Algorithm-Y machine has two heads on the Delta tape: reader `C` and
append-only writer `D`.  The ordinary machine represents that tape by

    left ++ [current] ++ reverse(front) ++ queue,

where `left` and `front` are stacks and `queue` is a strict FIFO containing the
unread appended tail.

### Lemma 3.1 — strict queue

The functional Hood--Melville queue implements FIFO `snoc`, `head`, and `tail`.

**Proof.** Give its rotation states the following abstract sequence, where `f`
and `r` are the public front and newly accumulated rear:

- `Idle`: `f ++ reverse(r)`;
- `Reversing(ok,fw,fp,ro,rp)`:
  `f ++ reverse(ro) ++ rp ++ reverse(r)`;
- `Appending(ok,fp,rp)`:
  `f ++ drop(|f|-ok,rp) ++ reverse(r)`;
- `Done(newf)`: `newf ++ reverse(r)`.

The preservation equations are finite and explicit.  Write juxtaposition for
concatenation.

- A reversing tick has `fw=x fw'` and `ro=y ro'`.  It changes these to
  `fw'`, `x fp`, `ro'`, `y rp`.  Since

      reverse(y ro') (rp) = reverse(ro') (y rp),

  the abstraction is unchanged.
- The last reversing tick has `fw=[]` and `ro=[y]`; replacing these by
  `Appending(ok,fp,y rp)` leaves `reverse(ro) rp = y rp`.
- An appending tick has `fp=x fp'` and changes `(ok,fp,rp)` to
  `(ok-1,fp',x rp)`.  The quantity `|f|-ok` increases by one, so dropping one
  additional leading item from `x rp` yields the same suffix as before.
- At `ok=0`, the invariant says all front items already prepended to `rp` are
  exactly the leading `|f|` items.  Installing `newf=rp` therefore makes the
  `Done`/`Idle` abstraction equal to the old one.
- During `Reversing`, invalidation decrements `ok`; this records that one item
  removed from the serving `f` must not be copied into the new front.  During
  `Appending` with `ok>0` the same decrement has that meaning.  With `ok=0`,
  the removed serving item is already the first item of `rp`, so removing that
  item from `rp` preserves exactly the tail of the old abstraction.
- `snoc(v)` replaces `r` by `v r`, and
  `reverse(v r)=reverse(r) [v]`; hence it appends `v`.  Public `tail` removes
  the first item of the serving `f`, while the invalidation cases above remove
  precisely its pending duplicate.

The length invariant `lenr<=lenf` before a public operation implies that a
rotation is started only at `lenr=lenf+1`.  A rotation requires `2|f|+1`
rotation ticks; the operation that starts it supplies two, and each of the next
`|f|` public operations supplies two more before the old serving front can be
exhausted.  Thus the phase side conditions used in the equations cannot fail.
The public operations therefore have FIFO semantics.  QED.

### Lemma 3.2 — imperative queue and stack compiler

The mutable queue in `strict_stack_queue.py` is bisimilar to Lemma 3.1's
functional queue.

Map a physical stack, whose top is at the Python-list end, to the reverse tuple.
Map `f1`, `rear`, `fwork`, `fp`, `rold`, and `rp1` to the corresponding
functional fields; `f2` and `rp2` are duplicate copies used in place of
persistent sharing.  Map the integer counters and phase literally.

Every branch in `_rotation_tick`, `_invalidate`, `snoc`, and `tail` is then the
same branch as the functional transition, with each tuple head/tail replaced
by one stack pop/push.  The assignments at rotation start and completion are
role changes; the ordinary compiler implements them by a finite permutation
of physical tape roles rather than by copying.  The duplicate invariants
`f1=f2` in `IDLE` and `rp1=rp2` during rotation are established on creation and
preserved by every paired write/pop.  Thus each mutable public operation
refines the corresponding functional operation.

The generated ordinary microprogram replaces each abstract primitive by the
following literal action:

- push: move right to virgin blank, then write the encoded value;
- pop: distinguish the bottom marker from a value, erase a value, and move
  left;
- reset: move right to virgin blank and write a new bottom marker;
- unary increment: move right and write `1`;
- unary decrement/test: distinguish bottom from `1`, erase `1`, and move left;
- role assignment: change only the finite `mapping` permutation in control.

The queue dispatcher has one task family for each mutable line:
`Q_SNOC`, `Q_TAIL`, `Q_INVALIDATE_APP`, `Q_CONSUME`, `Q_START`, the two
`Q_TICK` phase families, and completion.  Substituting the primitive meanings
above into each task gives exactly the corresponding mutable assignment, in
the same order.  All choices inspect only the same phase, counter-zero, or
stack-empty predicate as the mutable branch.  Thus a finite case induction on
the task tag proves that every command boundary represents one mutable queue
state and returns at the next command boundary with the state produced by the
requested public operation.  Therefore the ordinary table refines the mutable
queue.  QED.

### Lemma 3.3 — append/read zipper

Under the displayed materialization invariant:

- `append(v)` applies FIFO `snoc(v)`, so it appends `v` at the writer;
- `move_left` pushes `current` onto `front` and pops the rightmost item of
  `left`, so the materialized cells are unchanged and the reader moves left;
- `move_right` pushes `current` onto `left` and obtains the next cell first from
  `front`, then from the FIFO, so the materialized cells are unchanged and the
  reader moves right.

Lemma 3.2 supplies the FIFO semantics.  Hence the zipper exactly simulates one
append-only writer and one two-way reader.  QED.

### Lemma 3.4 — one ordinary source-step simulation

At an ordinary `DISPATCH` boundary, the direct tapes represent source heads
`A,B,S,T,U`, and the zipper represents source heads `C,D`.  The compiler:

1. selects the unique matching source schema using the direct symbols and
   cached `current` symbol of `C`;
2. performs the source writes and direct-head moves;
3. serially performs at most one Delta append and at most one `C` move through
   Lemma 3.3;
4. returns to the next source-state boundary.

The serialized operations touch storage disjoint from the direct tapes and use
the `C` symbol read at the boundary, so their order is observationally equal to
the source machine's simultaneous transition.  Lemmas 3.2--3.3 prove each
micro-operation.  Induction over source transitions proves a stuttering
simulation from the ordinary machine to Algorithm Y.  QED.

### Corollary 3.5

The ordinary Algorithm-Y table computes exactly the failure chain of its
prepared pattern.  The graph between source-step boundaries is finite and
acyclic; the checked-in generator computes its exact maximum as 103 ordinary
steps.  The bound is timing information, not part of semantic correctness.

## 4. The three prepared patterns

Starting from source tapes `$w!`, the checkpoint preparation loops write:

    PLAIN  = w,
    PREFIX = w @ reverse(w),
    SUFFIX = reverse(w) @ w.

This follows directly from the monotone source-head motions:
`PREP_FORWARD` copies `w`, `PREP_REVERSE` walks the reverse source from the last
symbol to the sentinel, and `PREP_SUFFIX` walks the forward source again.
Each target copy receives the same separator and endmarker, after which all
pattern heads are rewound to their retained sentinel.  Corollary 3.5 therefore
supplies exactly the three failure chains used in Corollary 1.4.

## 5. Meaning of the marker axes

All candidate axes have their permanent marker at coordinate zero.

### Lemma 5.1 — `PERIOD_TAPE`

When the PLAIN failure walk visits border length `b`, the controller head is at

    d = (n-b)/2

exactly when `n-b` is even; it writes `P` exactly in that parity.  By Lemma 1.1,
coordinate `d` is marked iff `2d` is a period of `w`.

**Proof of the coordinate.** At the first border, the helper walks from the
failure endpoint to the pattern end and advances the axis once per pair of
cells.  A backpointer walk moves the failure head left; the parity bit advances
the axis once per additional pair.  Thus the invariant is maintained for every
border in decreasing order.  QED.

### Lemma 5.2 — `FULL_TAPE`

When the PREFIX failure walk visits border length `l`, its axis is at `l/2`
exactly for even `l`.  It writes `V` only if `PERIOD_TAPE` is marked at the same
coordinate.  By Lemma 1.2, `FULL_TAPE[d]=V` iff the full branch accepts `d`.

### Lemma 5.3 — `PARTIAL_TAPE`

When the SUFFIX failure walk visits border length `l`, its axis is at
`n-l/2` exactly for even `l`; it writes `V` there.  At the sentinel it also
marks coordinate `n`, representing the empty suffix.  By Lemma 1.3,
`PARTIAL_TAPE[d]=V` iff the partial branch accepts `d`.

The coordinate arguments for Lemmas 5.2 and 5.3 are the same pairwise parity
induction as Lemma 5.1.  The prefix axis moves down from `l/2`; the suffix axis
moves up from `n-l/2` as border lengths decrease.

### Corollary 5.4 — union and least two

After rewinding, `MERGE` scans `FULL_TAPE` and `PARTIAL_TAPE` simultaneously at
coordinates `1,2,...`.  By Lemmas 5.2--5.3 their union is exactly `G(w)`.  The
controller writes the first union marker to `OUT1`, the next distinct marker to
`OUT2`, and halts at the explicit axis end if no second marker exists.  Thus the
output axes contain exactly the two least distinct gaps.  QED.

## 6. The `15d <= n < 16d` candidate test

At the beginning of the merge scan both source ratio heads scan the sentinel.
For each inspected gap coordinate, the `RATIO` loop advances `SRC_FWD` at most
15 cells and `SRC_FWD2` at most 16 cells, stopping either at `END` or after the
prescribed number of moves.  Induction on `d` gives

    SRC_FWD  = min(15d,n+1),
    SRC_FWD2 = min(16d,n+1),

where source coordinate `n+1` contains `END`.

Consequently

- `SRC_FWD` is not at `END` iff `15d <= n`;
- `SRC_FWD2` is at `END` iff `n < 16d`.

The candidate write is enabled only at the first union marker (`count=0`) and
only under both tests.  Corollary 5.4 proves that this first marker is
`min G(w)`.  This proves items 1--2 of `CheckpointCorrect`.  QED.

## 7. Reuse, retirement, and pause/resume

The reusable table lifts every nonterminal one-shot row verbatim.  Its only new
behaviour is entered from `RESULT_READY` by an explicit `RETIRE` request and
from clean `READY` by an explicit launch request.

### Lemma 7.1 — clean-READY representation

After retirement:

1. every result/working axis contains only its marker at relative coordinate 0
   and scans that marker;
2. each prepared pattern contains only its retained sentinel and scans the
   blank cell immediately to its right;
3. the forward source heads scan `END` and the reverse source head scans the
   sentinel;
4. every Algorithm-Y stack/counter tape scans the fixed initial symbol or a
   virgin blank immediately to the right of a fresh bottom/epoch marker.

**Proof.** `AXIS_REWIND/CLEAR` visits every coordinate through the explicit
partial-axis endmarker and erases all six axes in lockstep.  Each
`PATTERN_REWIND/CLEAR` traverses the contiguous prepared pattern through its
explicit `END`, erases it, and returns to the retained sentinel.  The source
loops stop only on their explicit terminal markers.  Each work-tape reset
abandons the old finite epoch, writes a fresh bottom marker in virgin blank,
and writes exactly the fixed initial top symbol when that tape has one.  The
loops are monotone and their terminal symbols are unique, so every clause holds
when the final reset reaches `READY`.  QED.

### Lemma 7.2 — fresh-execution equivalence

From clean `READY`, terminal-side source extension installs the three source
heads in the one-shot entry positions.  The launch row enters the exact
one-shot initial state in one transition.  By Lemma 7.1, every private tape is
a fresh one-shot initial tape up to an independent integer translation of its
new epoch.

Every one-shot row tests/writes only symbols and moves heads by `-1,0,+1`; it
contains no absolute coordinate.  The fresh bottom/epoch markers prevent a
valid run from entering an abandoned epoch.  Therefore per-tape translation is
a bisimulation between the reusable run and a fresh one-shot run.  Corollary
5.4 and Section 6 give identical results.  QED.

### Lemma 7.3 — result retention and pause/resume

At `RESULT_READY` the only enabled component transition requires the explicit
`RETIRE` symbol, so observing or pausing there leaves every output marker
unchanged.  At every nonterminal configuration the sparse table is
deterministic: all matching rows have the same action.  A pause performs no
transition, so resuming continues the unique suffix of the same run.  The
frozen source is never written by a checkpoint row.  Therefore arbitrary
pause/resume segmentation cannot alter the result.  QED.

Lemmas 7.1--7.3 prove items 3--4.

## 8. Persistent Lemma-3.3 candidate semantics

Suppose a frozen scan of a word `q` returns candidate `d`.  By Sections 5--6,

    d=min G(q),   15d <= |q| < 16d.

In particular `|q|>2d`, so `d` is in the full branch: `q` has period `2d` and
its first `2d` symbols form `x reverse(x)`.

### Lemma 8.1 — extension survival

For any extension `qv`, the same `d` remains in `G(qv)` exactly while every new
symbol agrees with the symbol `2d` positions earlier.

**Proof.** The palindromic prefix of length `2d` is already fixed in `q`.
Membership of the full branch on an extension therefore has only the period
condition left, and extending a word of period `2d` preserves that period
exactly under the stated comparisons.  QED.

### Lemma 8.2 — no smaller candidate appears

If `e<d`, then `2e<|q|`.  Thus `e` was already a full-branch query at `q`.
Because `d=min G(q)`, some equality required for period `2e` or its fixed
palindromic prefix already failed inside `q`; extension cannot repair it.
Hence no `e<d` can enter `G(qv)`.  QED.

### Lemma 8.3 — target emission

The retained terminal prepositions its lag head by `2d`, compares each catch-up
and following symbol with that lag, and records permanently whether a mismatch
has occurred.  By Lemma 8.1 the `GOOD/BAD` state is exactly the survival of `d`.
At target length `16d`, the controller emits exactly in `GOOD`.  Lemma 8.2 then
makes `d` the least gap.  Conversely, every emitted `d` is therefore the least
gap at a length exactly `16d`.  QED.

For completeness in the other direction, consider a prefix `u` with
`|u|=16d` and `d=min G(u)`.  Frozen candidates smaller than `d` may be tried
and later invalidated, but each such failure is permanent.  The proved
`BackgroundCatchUp` theorem guarantees that cleanup, relaunch, and catch-up
finish before the next SG target and in particular that the scan whose live
candidate is `d` is installed early enough to follow it to `u`.  Lemma 8.1
then keeps it `GOOD`, so Lemma 8.3 emits it.  Thus the terminal emits exactly
`lemma33_t1_discovered_gap`.  This proves item 5.

The use of `BackgroundCatchUp` here is legitimate and noncircular: its timing
proof assumed only the frozen checkpoint result theorem established in
Sections 1--7; it did not assume the terminal's semantic output theorem.

## 9. RECOVER and LOCAL wrappers

`RECOVER` runs the checkpoint on the active suffix after the anchor.  By
Corollary 5.4 its marker positions are the least two finite active gaps.  Adding
the anchor translates them to the corresponding midpoint positions.  If fewer
than two are present, the wrapper appends `RIGHT+1`, then `RIGHT+2`; these are
the standard automatic future candidates.  Sorting therefore returns exactly
the first two candidates.

`LOCAL` freezes exactly the supplied prefix of at most `4r` active symbols,
runs the same checkpoint, and selects the first returned gap at most `r`.
Corollary 5.4 proves this is exactly the least candidate in that bounded query.
This proves item 6.

## 10. Ordinary history terminal

The retained source and lag cursors are lowered through the same append/read
zipper proved correct in Lemmas 3.1--3.3.  `prepare_comparison(2d)` moves the lag
cursor exactly `2d` represented cells behind the live cursor.  Each
`compare_next` moves both one cell right and compares the represented symbols.
Therefore the ordinary terminal performs exactly the comparisons used in
Lemma 8.1.  Its command compiler is the Algorithm-Y storage compiler projected
to the zipper tapes, so Lemmas 3.2--3.3 apply unchanged.

## 11. Dependency ledger

### Proved here

- failure-chain characterization of every specialized Lemma-3.2 gap;
- source Algorithm-Y correctness;
- strict queue, zipper, and ordinary lowering refinement;
- exact meaning of all checkpoint marker axes;
- first-two merge and candidate-ratio logic;
- reusable fresh-epoch equivalence;
- result retention and pause/resume;
- persistent candidate survival, rejection, and emission semantics;
- RECOVER and bounded-query LOCAL checkpoint semantics.

### Imported proved result

- `BackgroundCatchUp`, used only to establish that the semantically correct
  scan/follow process cannot miss a target because of insufficient time.

### Not part of `CheckpointCorrect`

- the outer case-3 local-window/Fine--Wilf reduction from a full active suffix
  to the first `4r` symbols;
- primitive predictability bounds for cases 1--4;
- the final six-case `need <= C*avail + D` theorem;
- Galil scheduler regeneration;
- the later scaffolding-to-PEG theorem.

## 12. Mechanical correspondence checks

The accompanying tests and certificate check that the proof refers to the
current source:

- exhaustive equality of the direct and failure-chain gap specifications for
  all binary words through length 13;
- exhaustive ratio-head arithmetic for `1<=n<=512`;
- the literal ordinary checkpoint against the independent specification for
  all binary words through length 7;
- exact row-for-row lifting of every nonterminal one-shot state into the
  reusable table;
- acyclicity and exact 103-step maximum between Algorithm-Y source boundaries;
- the existing ordinary/reusable/history/persistent regressions.

These finite checks are labelled computational evidence.  The universal claim
is supplied by the lemmas above.