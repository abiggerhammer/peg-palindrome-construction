# Sparse ordinary-TM table format

The generated `*.json.gz` files are complete finite transition tables for
ordinary one-head-per-tape Turing machines.  They use finite wildcard schemas
to avoid printing copies of a row which differ only on ignored tapes.

Each row has the form

```text
[state_id, reads, next_state_id, writes, moves]
```

For tape `i`:

- `reads[i]` is a literal symbol, a finite list of accepted symbols, or `null`
  for every symbol in that tape's declared finite alphabet;
- `writes[i]` is a literal symbol or `null` to preserve the scanned symbol;
- `moves[i]` is `-1`, `0`, or `1`.

A row performs exactly one simultaneous ordinary TM transition.  Expanding all
`null` and finite-set read atoms gives the conventional concrete table.
Overlapping schemas are permitted only when they denote the same action.

## Algorithm Y tape layout

`algorithm_y_ordinary_table.json.gz` has 17 tapes:

1. private pattern copy for source head A;
2. private pattern copy for source head B;
3. source counter tape S;
4. source counter tape T;
5. source scratch tape U;
6. zipper left stack;
7. zipper front stack;
8–15. eight physical queue-stack tapes;
16. unary `ok` counter;
17. unary `budget` counter.

Every stack head scans its top element, or `B` when the current stack epoch is
empty.  A reset writes a fresh `B` to the right and abandons the previous epoch;
it never traverses stale cells.  The eight queue roles are assigned to physical
stack tapes by one of twelve reachable finite permutations.

The exact graph-theoretic maximum from one Algorithm-Y source dispatch to the
next is 103 ordinary TM microsteps.

## Sparse-map v2 rows

`checkpoint_ordinary_table.json.gz` uses a more compact but equivalent row
encoding because its machine has 63 tapes.  Each row is

```text
[state_id, reads_map, next_state_id, writes_map, moves_map]
```

where each map is represented as a sorted list of `[tape_index, value]` pairs.
A tape omitted from `reads_map` is a finite-alphabet wildcard; a tape omitted
from `writes_map` preserves its scanned symbol; and a tape omitted from
`moves_map` stays in place.  Read values are literals or finite lists.  Thus
this format is simply the v1 format with default entries elided; it still
expands mechanically into a conventional concrete transition table.
