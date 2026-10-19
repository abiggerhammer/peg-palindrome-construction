# Fixed constant-speedup application

Date: 2026-07-25

## Input theorem

The factored scheduled machine is a deterministic ordinary multitape
input/output machine with fixed bounded delay

    K = 416,945,810,716

ordinary transitions per physical input symbol.

Galil's real-time convention allows a fixed number of transitions between
successive reads and explicitly invokes the Hartmanis--Stearns constant-speedup
theorem to obtain the conventional one-transition-per-read definition.
Hartmanis and Stearns prove their speedup theorem constructively: for factor
`1/2`, pairs of old tape symbols are combined into new symbols, adjacent
information is kept in finite control, and two old operations are tabulated as
one new operation.  Iteration gives factor `1/2^m`.

## Exact factor

The least power of two dominating `K` is

    2^39 = 549,755,813,888,

because

    2^38 = 274,877,906,944 < K <= 2^39.

Therefore 39 iterations of the constructive halving transformation provide one
new transition with capacity for every old transition between two successive
physical reads.  The unused capacity is

    2^39-K = 132,810,003,172

old transitions per input interval.

For this online application the read-only input tape is left unblocked.  During
an old input interval its head stays on the current symbol until the final output
row, so the entire old microtrace depends only on that symbol and the encoded
work-tape neighborhoods, never on an unread future symbol.  At a physical-read
boundary, the sped-up transition reads the same current symbol, executes the
finite tabulated old microtrace until the old machine emits its output, performs
that output and the single input-head move, and ignores the remaining capacity.
It therefore emits exactly one correct output per input symbol in one
conventional transition.

## Theorem

There is an effectively constructible conventional real-time multitape Turing
machine recognizing the even-palindrome language, obtained from the composed
bounded-delay machine by 39 iterations of the Hartmanis--Stearns pair-symbol
speedup.

This is an application of an imported proved theorem, not a new proof of the
entire Hartmanis--Stearns construction.  The application is explicit in the
following senses:

- the old machine is the exact finite factored machine certified in the
  companion composition proof;
- the old delay is the explicit integer `K` above;
- the number of halving iterations is exactly 39;
- the resulting macro capacity and slack are exact;
- every theorem side condition is checked in the machine-readable certificate.

## Representation boundary

The sped-up machine is finite and effective, but its paired block alphabets and
finite control are astronomically large.  They are intentionally retained as a
39-layer symbolic Hartmanis--Stearns representation rather than enumerated.

Thus the real-time existence theorem is discharged.  The remaining engineering
obligation for an emitted PEG is to teach the sparse scaffolding compiler to
consume this factored speedup representation—or equivalently to compile the
bounded-delay machine by symbolic macro-closure—without enumerating the giant
block alphabet.

## Status

**Proved by imported theorem application**

- applicability of fixed constant speedup;
- exact 39-iteration factor;
- conventional real-time recognition.

**Not materialized**

- the enormous final finite-control table and paired block alphabets.

**Still required for the explicit PEG artifact**

- a symbolic speedup/scaffolding compiler;
- scheduler-inclusive PEG differential tests.