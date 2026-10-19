# Research notes: real-time machines, scaffolds, and palindromes

## Current theorem implemented by the code

Let `M` be a deterministic multitape Turing machine with:

- finitely many work tapes and a finite work alphabet;
- one input symbol supplied to the finite control per clock tick;
- exactly one ordinary local work-tape transition per supplied symbol;
- acceptance determined by the state immediately after the last symbol.

Then the compiler in `realtime_mtm.py` constructs a finite PEG `G_M` such that

```text
L(G_M) = reverse(L(M)).
```

This is an explicit instance of the route

```text
real-time multitape TM -> radius-2 scaffolding automaton -> PEG.
```

## Persistent zipper invariant

For tape `i`, scaffold edge types `2i` and `2i+1` represent the left and right stacks. Each new scaffold node stores finite fields

```text
head[i], left_top[i], right_top[i].
```

The logical stack represented at a node is recovered recursively from its top field and corresponding edge. The compiler never copies an unbounded stack; it creates one new version node and shares unchanged tails.

### Move right

After writing `b`,

```text
(L, h, R) -> (bL, head(R), tail(R)).
```

The left stack is pushed by pointing its new tail to the old node. The right stack is popped by reading its old top field and following its edge twice to obtain the new tail.

### Move left

Symmetrically,

```text
(L, h, R) -> (tail(L), head(L), bR).
```

### Stay

Only the head field changes; both stack edges and top fields are retained.

## PEG compilation invariant

For every input prefix `x`, the generated PEG nonterminals evaluated on `reverse(x)` encode:

- the real-time machine state after `x`;
- each current tape-head symbol;
- each zipper-stack top symbol;
- each scaffold path of length at most two.

Every transition predicate first consumes—or looks across—the newest input terminal before consulting the representation of the preceding configuration. This makes the recursive definitions well-founded in the ordinary PEG sense.

## Validation performed

The code has been checked in three ways:

1. direct examples with known languages;
2. an independent operational simulator for the source Turing machine;
3. randomized differential testing of arbitrary total transition tables, including left and right movement, rewriting blank and nonblank cells, revisiting old cells, and two simultaneous work tapes.

These tests establish confidence in the compiler implementation, not the still-missing palindrome front end.

## Narrowed palindrome target

Seiferas and Galil give real-time multitape recognizers for the fixed-ratio reversal family

```text
{ w x y x^R z : |w| = r|x|, |y| = s|x|, |z| = t|x| }
```

for arbitrary fixed `r`, `s`, and `t`. At `r=s=t=0`, this is precisely the even-palindrome language `{x x^R}` conjectured by Loff, Moreira, and Reis not to have a PEG.

That specialization is a better extraction target than Slisenko's more general machine, which reports every palindromic prefix.

## Unresolved engineering/proof obligation

The literature proves that the real-time machine exists but does not present a ready-to-import finite transition table. A valid final artifact must therefore do one of the following:

1. lower the published Seiferas–Galil macro algorithm to elementary transitions and prove the per-symbol step bound; or
2. give a new explicit real-time algorithm in the source-machine model; or
3. bypass the machine and give a direct finite scaffolding automaton or direct PEG.

Until one of those is completed, generating a file named `palindrome.peg` would overstate the result.

## Rejected shortcut: ordinary online palindrome trees

Modern online palindrome data structures can update quickly on a RAM, but their mutable dictionaries and arbitrary node access do not automatically translate to a bounded-radius immutable scaffolding update. The issue is not storage capacity; it is making every required pointer reachable from the previous top through a uniformly bounded path.

## Lemmas 3.2 and 3.3: equal-input specialization

At `r=s=0`, `B2=B3`, so both strings passed to Lemmas 3.2 and 3.3 are the same
active suffix `A`.  For a positive gap `d`, the two branches of Lemma 3.2 reduce
to:

```text
2d <= |A|:  2d is a period of A and A[:2d] is an even palindrome;
2d >  |A|:  A[2d-|A|:] is an even palindrome centred at d.
```

`lemma32_t1.py` enumerates all such gaps in linear indexed time.  Lemma 3.3
then accepts `(A,A)` precisely when `|A|=c*d` and `d` is the least positive
Lemma-3.2 gap.  This predicate now drives the case-5 background completion,
removing the final semantic oracle from the read loop.

## Extracted machine macros from the new papers

Galil's Turing-machine KMP stores `Delta(i)=1+P(i)-P(i+1)` as unary blocks.
The jump length `i-P(i)` is the total number of unary ones before the relevant
block.  `fp_delta.py` implements the block representation, backpointer walk,
and match advance with exact unary distances.

Galil's predictability conversion is now executable in
`predictability_scheduler.py`: the simulated and physical input heads run
together in fast mode; after `2c` unfinished microsteps the physical head
speculates a zero and advances; in slow mode it advances every `2c` simulation
steps until the simulated head catches it.

These are still macros rather than flattened TM states.  The remaining work is
to choose a single primitive tape layout, expand unary traversals and counter
updates cell by cell, compose the parallel machines, and run the existing
multitape-to-PEG compiler.

## 2026-07-23: cell-level unary-Delta lowering

Galil's Section 4 description was lowered to a fixed four-tape microprogram.
The Delta tape has one head; the jump counter `S` and two scratch unary tapes
have one head each.  A backpointer walk copies `S` to two scratch counters,
restores the `S` head, moves the Delta head left across exactly `lambda(p)` zero
boundaries, and removes one `S` mark for every Delta `1` crossed.  No transition
moves more than one cell, and the state set is independent of the pattern.

The delayed-update variant now executes those same primitive transitions.  It
can pause in the middle of a Delta block after a successful match and resume on
later input.  Before a mismatch uses a failure link, all pending advances are
completed, matching Galil's construction.

The fast/slow predictability controller is also represented as a finite table:
its only unrolled counter ranges over `0..2c-1`.  Differential tests compare the
table executor with the earlier abstract scheduler.
