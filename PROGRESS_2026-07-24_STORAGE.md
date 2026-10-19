# Progress: eliminating the final shared tape

This update replaces the remaining multihead-storage assumption by an
executable strict real-time data structure.

## Read-only shared tapes

`readonly_multihead_lowering.py` duplicates every read-only shared tape once
per logical head.  This is an exact zero-slowdown transformation.

- The three-head frozen source tape in `pattern_prepare_multihead.py` now lowers
  completely to an ordinary six-tape machine.
- Algorithm Y's two read-only pattern heads A and B now have private copies.
- The only shared unit left after duplication is the unary-Delta tape with C as
  a preserving two-way reader and D as a right-moving append-only writer.

`generated/storage_lowering_inventory.json` records and mechanically audits
these properties.

## Append/read storage

The residual unit is represented as

```
reverse(left) + current + front + queue
```

where `left` and `front` are ordinary stacks and `queue` is a strict
Hood--Melville FIFO.  A C-left move pushes `current` onto `front`; a C-right
move pops `front`, or dequeues the FIFO when `front` is empty; D appends to the
FIFO.

- `hood_melville_queue.py` is the functional real-time reference.
- `strict_stack_queue.py` removes persistence by keeping two physical front
  copies and performs at most 20 individual stack/counter primitives per FIFO
  operation in the current conservative accounting.
- `strict_append_read_zipper.py` combines the queue with the two cursor stacks.
- `algorithm_y_strict_storage.py` runs the original literal Algorithm-Y source
  table over this representation.

Exhaustive tests through binary pattern length 10, plus separator-bearing
patterns, produce exactly the same unary-Delta blocks and source-step counts as
the original multihead table.  A source transition performs at most one append
and one C move, and the measured storage bound is at most 40 primitive
stack/counter operations.

## Exact remaining boundary

No shared random-access tape remains at the data-structure level.  The final
mechanical lowering is now:

1. encode each of the fixed stacks/counters as one ordinary tape;
2. expand each push/pop/increment/decrement into one- or two-cell TM states;
3. take the product with Algorithm Y, the SG/Lemma-3.3 controllers, and Galil's
   scheduler;
4. bundle the resulting fixed microstep budget per input symbol;
5. emit `palindrome.peg` through the existing zipper compiler.

The unresolved item is table expansion and product construction, not another
algorithmic or storage theorem.
