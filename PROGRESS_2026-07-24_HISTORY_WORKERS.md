# Ordinary history terminal and worker milestone

## History zipper table

`history_zipper_ordinary_tm.py` projects the already audited strict
Hood--Melville queue microprogram onto a standalone append/read zipper.  The
result has:

- 12 ordinary one-head tapes;
- 88,070 finite states;
- 139,352 sparse one-cell rows;
- explicit entry states for `APPEND0`, `APPEND1`, `LEFT`, and `RIGHT`.

The read symbol, rotation phase, and queue-role permutation live only in finite
control.  Randomized differential tests execute 2,500 mixed operations against
`StrictAppendReadZipper`.

## Three-cursor terminal

`ordinary_history_terminal.py` uses three independent copies:

1. `CURRENT`, for post-checkpoint input;
2. `LAG`, for the symbol one candidate period earlier;
3. `COPY`, for monotone checkpoint source extension.

Incoming symbols are appended by literal zipper rows.  Checkpoint source tapes
are initialized and extended one cell at a time; no Python bulk source update is
used.  CATCH_UP and FOLLOW comparisons are performed by the two zipper readers,
not by indexing a host string.

`lemma33_checkpoint_terminal.py` connects this terminal to the reusable
64-tape checkpoint machine.  Selected long inputs and exhaustive binary inputs
through length four agree with the semantic Lemma 3.3 audit.

## Ordinary RECOVER and LOCAL workers

`ordinary_lemma32_worker.py` composes the same terminal with the ordinary
checkpoint table:

- `RECOVER` reads the first two marked gaps and adds the automatic future gap
  when fewer than two candidates lie inside the frozen word;
- `LOCAL` scans only the proof-authorized first `4d` active symbols and selects
  the first marked gap at most `d`.

The SG executor now supports:

```python
background_scan_backend="ordinary_terminal"
lemma32_backend="ordinary_checkpoint"
```

With those settings every selected worker is implemented by ordinary
one-head-per-tape table rows.  The remaining host abstraction is the *outer*
SG cursor product: selecting the active suffix at B3, promoting B3', and
reading/installing unary worker-result markers.

## Sparse real-time PEG backend

`sparse_realtime_mtm.py` adds a direct compiler from sparse real-time ordinary
TM rows to PEGs.  Wildcard read tapes are not Cartesian-expanded.  Preserved
symbols are split only on the individual tape whose update depends on them.
Differential tests cover wildcard rows, preserved writes, left/right moves, and
distinct alphabets on different tapes.
