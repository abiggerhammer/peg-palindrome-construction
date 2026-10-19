# Palindrome-to-PEG workbench

## Latest table-production milestone

See `PROGRESS_2026-07-24_TABLES.md`.  The archive now contains complete sparse
one-cell ordinary-TM tables for pattern preparation and Fischer--Paterson
Algorithm Y, including a compressed 198,751-row table and its format
specification.


This repository is an executable research prototype for the following route:

1. describe a deterministic real-time multitape Turing machine;
2. represent each work tape as a persistent zipper in a scaffolding automaton;
3. compile that scaffolding computation into an ordinary parsing expression grammar (PEG) recognizing the reverse language.

The intended final target is the binary even-palindrome language.  The repository now contains the complete corrected bounded-delay palindrome machine and an exact finite indexed presentation whose exhaustive expansion is an ordinary PEG for that language.  The concrete grammar text is astronomically large and is therefore retained as a checked generation plan rather than physically printed.

## Main modules

- `peg.py` — a small standard PEG AST, packrat recognizer, and Ford-style serializer.
- `scaffold.py` — an executable symbolic scaffolding-automaton model.
- `compile_sa_to_peg.py` — a direct implementation of the sufficient direction of Loff–Moreira–Reis Theorem 16: a scaffolding automaton for `L` becomes a PEG for `reverse(L)`.
- `realtime_mtm.py` — a direct factored compiler from a deterministic one-step-per-input-symbol multitape Turing machine to a PEG for its reverse language.

## Why the zipper compiler works

A work tape is represented by `(L, h, R)`, where `h` is the scanned symbol and `L` and `R` are persistent stacks, nearest cell first. Each stack snapshot consists of a finite top-symbol field and one scaffold edge to its tail.

A local Turing-tape operation needs only bounded scaffold paths:

- retain a stack: path length 1;
- push: the new tail is the old top node (empty path);
- pop: the new tail is reached by following the same stack edge twice.

Thus radius 2 suffices, independently of input length. The generated PEG reconstructs those persistent snapshots while reading the input in reverse.

## Tests

Run:

```sh
pytest -q
```

The suite currently includes:

- a hand-written scaffolding automaton using persistent push/pop;
- a moving-head real-time Turing-machine example;
- differential tests on twelve randomly generated total real-time machines, including two-work-tape machines, over every binary input through length 5.

For every tested machine `M` and string `x`, the invariant checked is:

```text
compiled_peg.recognize(reverse(x)) == M.run(x)
```

## Generated examples

- `generated_1n0n.peg` recognizes `{1^n 0^n | n >= 0}`.
- `generated_1nplus1_0n.peg` recognizes the reverse of the language accepted by `examples/realtime_stack_tm.py`.

Regenerate them with:

```sh
python examples/anbn.py
python examples/realtime_stack_tm.py
```

## Remaining front-end task

The missing input is a completely explicit finite transition system for a deterministic real-time palindrome recognizer. The cleanest immediate target is the Seiferas–Galil real-time recognizer for

```text
{ w x y x^R z : |w| = r|x|, |y| = s|x|, |z| = t|x| }
```

specialized to `r = s = t = 0`, which is exactly `{x x^R}`.

The published algorithm is described at a macro level rather than as a flat transition table. Lowering those macros without hiding unbounded work is the current research task. Once that table exists, `compile_realtime_mtm_to_peg` mechanically emits the ordinary finite PEG.

## Seiferas--Galil zero-ratio audit

The full paper has now been specialized to `r=s=0`:

* `seiferas_galil_specialization.md` gives the mathematical reduction;
* `sg_zero_ratio.py` is the exact reference model and Lemma 3.1 checker;
* `lemma32_t1.py` gives a linear equal-input specialization of Lemma 3.2
  using a Z-array and Manacher even-palindrome radii;
* `lemma33_t1.py` collapses Lemma 3.3 to the first-candidate-at-ratio test;
* `sg_zero_ratio_machine.py` uses those implementations in all six branches,
  so no branch consults the direct palindrome oracle;
* `fp_delta.py` makes the Fischer--Paterson unary-delta failure-tape encoding
  and its two head operations executable;
* `predictability_scheduler.py` implements Galil's explicit fast/slow
  predictability scheduler;
* the tests exhaustively audit these specializations and the compiler backend.

Run:

```bash
pytest -q
python sg_zero_ratio.py
```

## Current extraction boundary

The semantic black boxes in Lemmas 3.2 and 3.3 have now been removed for the
`r=s=0` equal-input case.  What remains before a generated palindrome PEG is a
primitive-machine lowering: expand the indexed Z/Manacher scans (or replace
them with the equivalent Fischer--Paterson forced-mismatch macros), unary block
walks, counter updates, parallel schedules, and Galil fast/slow scheduler into
a finite one-head-per-tape transition table.

## Primitive lowering milestone

The workbench now contains two additional layers below the previous macro
models:

- `flat_tm.py` is a literal deterministic one-cell multitape transition-table
  interpreter with wildcard rules expanded at construction time.
- `fp_delta_micro.py` lowers Fischer--Paterson/Galil `C,S` operations to a
  fixed four-tape table.  Advancing one match, copying/restoring the unary jump
  counter, crossing exactly `lambda(p)` block delimiters, and decrementing the
  jump counter are all performed one cell per transition.  The same operation
  can be paused and resumed after any microstep.
- `DeferredDeltaKMPMatcher` implements Galil's delayed `C,S` update: successful
  matches receive only a fixed microstep budget; a mismatch drains the pending
  updates and then follows unary failure links.
- `scheduler_control_table(c)` expands Galil's fast/slow scheduler into finite
  states `(mode, clock)` and a literal table driven only by source completion
  and head coincidence.

These additions remove block-walk and scheduler pseudocode from the remaining
front end.  The unresolved work is composing the two specialized Lemma 3.2
matchers and the Lemma 3.3 background recognizer as one online primitive
machine, then applying the scheduler table and the existing PEG backend.

`lemma32_failure.py` removes the remaining algorithmic dependence on Z and
Manacher arrays.  It derives the same candidate gaps from three KMP border
chains: the active word, `word + $ + reverse(word)`, and
`reverse(word) + $ + word`.  Exhaustive tests compare this failure-link form
with the independent Z/Manacher implementation over every binary word through
length 13.

`build_failure_delta_micro()` now constructs the failure chain and Delta blocks
left-to-right without calling the indexed failure-function implementation.  It
uses only character comparisons, previously constructed blocks, and the flat
cell-level `advance`/`backpointer` programs.  Exhaustive tests compare the
result with the independent reference implementation.

`lemma32_micro.py` composes three self-built unary-Delta failure tapes and walks
their border chains through the flat backpointer table.  It now supplies the
operational `RECOVER`, `LOCAL`, and Lemma-3.3 background decisions in
`SGZeroRatioMachine`; Z/Manacher and indexed failure implementations remain
only as independent test oracles.

## Persistent-background and controller milestone

The retained Lemma 3.3 process is now executable with the explicit
`algorithm_y_tape` backend.  The default operational configuration disables all
reference oracles; `audit=True` reenables them solely as assertions.

Additional modules:

- `lemma33_persistent.py` retains one frozen checkpoint scan across physical
  input symbols, catches its heads up, and follows the selected period to the
  unique target length.
- `lemma33_controller.py` exports the complete 576-entry finite phase table.
- `sg_controller.py` exports the complete 16-entry outer six-case table.
- `lemma32_y_tape.py::next_candidate_y_tape_local` implements the paper's
  small-gap optimization by scanning only the first `4d` active symbols.
- `construction_constants.py` and `explicit_bounds.md` give conservative
  numerical constants for the checkpoint and Galil schedulers.
- `sg_scheduler_audit.py` executes the complete source trace through Galil's
  finite table, including genuine SLOW-mode/speculative-zero runs.
- `palindrome_machine_spec.py` exports a machine-readable inventory to
  `generated/palindrome_machine_spec.json`.

The remaining boundary is multihead-storage lowering, not Lemma 3.3
persistence.  See `NEXT_STEPS.md`.

## Final shared-tape elimination milestone

`readonly_multihead_lowering.py` exactly duplicates read-only shared tapes.
`strict_stack_queue.py` and `strict_append_read_zipper.py` replace Algorithm Y's
sole remaining C/D shared tape with ordinary stacks plus a strict real-time
FIFO.  `algorithm_y_strict_storage.py` differentially executes the unchanged
Algorithm-Y transition table on this storage and agrees exhaustively through
binary pattern length 10.  See `PROGRESS_2026-07-24_STORAGE.md`.

## Reusable ordinary checkpoint milestone

`checkpoint_reusable_tm.py` adds explicit fresh-epoch reset paths to the
63-tape checkpoint body.  Its exported 64-tape table has 484,701 states and
766,211 sparse rows.  `lemma33_checkpoint_ordinary.py` retains that table
across input symbols under the finite Lemma 3.3 phase controller, and the SG
machine can select it with `background_scan_backend="ordinary_checkpoint"`.
See `PROGRESS_2026-07-24_PERSISTENT_TABLE.md` for the exact remaining terminal
and worker-product boundary.

## Ordinary history and all-worker milestone

`history_zipper_ordinary_tm.py` exports a 12-tape, 88,070-state,
139,352-row strict append/read terminal.  `ordinary_history_terminal.py` uses
three copies to eliminate bulk checkpoint-source updates and host-string
CATCH_UP/FOLLOW comparisons.  `ordinary_lemma32_worker.py` and
`lemma33_checkpoint_terminal.py` put RECOVER, LOCAL, and BACKGROUND on ordinary
one-head-per-tape machinery.  The SG audit executor can select all of them with
`lemma32_backend="ordinary_checkpoint"` and
`background_scan_backend="ordinary_terminal"`.

`sparse_realtime_mtm.py` now compiles finite wildcard rows directly to PEG
without Cartesian expansion over ignored tape symbols.  See
`PROGRESS_2026-07-24_HISTORY_WORKERS.md` for the exact remaining outer-product
boundary.


## Latest stage: registered outer dispatcher

See `PROGRESS_2026-07-24_OUTER_DISPATCH.md`.  The global registered worker
fabric and the complete six-case input dispatcher are now emitted as sparse
one-cell ordinary-TM rows.  Cases 1 and 4, including source output and true
fresh-epoch background-history reset, are complete.  Cases 2, 3, 5, and 6
remain to be attached before scheduler composition.

## Latest stage: retained outer/result lowering

See `PROGRESS_2026-07-24_OUTER_INCREMENTAL.md`.  Candidate marker discovery,
`16d` target accounting, comparison-start detection, and background-gap
installation now use retained ordinary tapes/cursors.  A registered-component
service wrapper provides pause/resume composition without multiplying the
large worker state sets.  The final outer microcontroller table and scheduler
product remain to be emitted before `palindrome.peg`.

## Latest durable stage: all six outer cases rebuilt

`sg_outer_remaining_cases.py` now contains durable literal ordinary-table
programs for cases 2, 3, 5, and 6.  Together with the dispatcher and constant
cases, repeated execution reaches `SOURCE_DONE_0/1` through every SG case.
Case 5 retains a paused ordinary checkpoint across input symbols; case 6 can
resume and drain that exact state before shared RECOVER.

The production unscheduled source inventory is 224 tapes, 1,562,428 states,
and 5,225,334 sparse one-cell rows.  See
`PROGRESS_2026-07-24_REBUILT_CASES.md` and
`generated/sg_source_row_manifest.json`.  The remaining boundary is Galil
scheduling and the fixed-speed lowering needed before PEG emission.

## Latest stage: symbolic bounded-delay PEG compiler

`bounded_delay_macro_compiler.py` compiles small finite bounded-delay ordinary
multitape machines through aligned block scaffolds to literal ordinary PEGs.
`succinct_block_peg.py` and `compile_palindrome_succinct_peg.py` apply the same
construction to the 295-tape scheduled palindrome machine while retaining the
`2^39`-cell blocks and repeated-square macro closure as finite indexed rule
families.  The generated checkpoint is
`generated/palindrome_reverse.speg.json`.

The block construction has scaffold degree 590 and radius 2.  Reduced-machine
literal expansions agree differentially with their source machines.  The full
indexed presentation is finite and deterministic, but is not yet being claimed
as a publication-level explicit palindrome PEG pending an independent audit of
its indexed expansion against the formal Loff--Moreira--Reis scaffolding
construction.  See `PALINDROME_PEG_COMPILER_CHECKPOINT_2026-07-25.md`.

## Latest stage: exact finite ordinary-PEG existence checkpoint

`indexed_block_macro_expander.py` and `lmr_rule_expander.py` now give the
on-demand ordinary-rule expansion.  The full schema uses exactly the standard
`State`, `Label`, `Neighbourhood`, `Path`, `Transition`, and
`AutomatonAccepts` families.  A unique one-use initial state and an explicit
rejecting sink make the scaffolding transition function total over the complete
finite radius-two neighbourhood domain.

The resulting internal theorem is that exhaustive expansion of
`generated/palindrome_reverse.speg.json` produces a finite ordinary PEG for all
binary even palindromes.  See
`PALINDROME_PEG_EXISTENCE_CHECKPOINT_2026-07-25.md` and
`PALINDROME_INDEXED_PEG_AUDIT_2026-07-25.md`.  This is a proved construction
checkpoint, not a claim of independent external or publication-level review.
