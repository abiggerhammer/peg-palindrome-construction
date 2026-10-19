# Proof overview — even palindromes are PEG-recognizable (proposed)

**This is an audit guide, not a substitute for the detailed proofs. No independent review or proof-assistant certification has been completed.**

## Statement

Let `EPAL = { ww^R : w in {0,1}* }`, including the empty word. The July 25 construction claims that there is a finite standard PEG `G` for which `L(G) = EPAL`, contradicting Conjecture 7 in Loff–Moreira–Reis (JCSS 2020) if the proof is correct.

## Dependency chain

**1 — Language-specific online recognizer.** The project specializes and corrects a Seiferas–Galil procedure for binary even palindromes. It replaces abstract algorithmic steps with an ordinary finite-control multitape source machine. See `CHECKPOINT_CORRECT_PROOF_2026-07-25.md`, `BACKGROUND_AND_CASE6_PROOF_2026-07-25.md`, and `CASES_1_4_PREDICTABILITY_PROOF_2026-07-25.md`.

**2 — Uniform availability bound and scheduling.** The six-case predictability proof establishes a structural bound of `need(u,a) <= 947906 * avail(u,a) + 1782767609` for the specialized source machine. Galil's FAST/SLOW scheduler is compiled to finite ordinary transitions. See `SIX_CASE_PREDICTABILITY_THEOREM_2026-07-25.md`, `GALIL_SCHEDULER_TRANSLATION_2026-07-25.md`, and `SCHEDULER_SOURCE_COMPOSITION_PROOF_2026-07-25.md`.

**3 — Bounded-delay machine.** After composition, there are at most `K = 416945810716` primitive transitions per input symbol, on a fixed number of work tapes. A separate constant-speedup argument is recorded in `FIXED_SPEEDUP_APPLICATION_2026-07-25.md`. The *indexed PEG* pipeline instead directly consumes the bounded-delay version; its enormous constant is not meant to be practical.

**4 — Finite radius-2 scaffolding automaton.** Partition every work tape into aligned blocks of `B = 2^39` cells, so `K <= B`. Per input symbol, a head can visit only the current block and its immediate neighbors; the proof's locality lemma rules out a two-sided changed-neighbor conflict at interval end. Each new scaffold node holds finite block labels, with two persistent-stack edges per tape to preserve remaining history. A radius-2 neighborhood supplies enough information for each update. For formal totality, the transition function includes a one-use initial state and a rejecting sink for malformed or unreachable formal neighborhoods. The finite tape/block alphabets and finite neighborhoods imply an *effective* transition-function enumeration.

**5 — Ordinary PEG compilation.** The sufficient direction of the Loff–Moreira–Reis characterization maps a scaffolding automaton for a language `L` to an ordinary PEG recognizing `L^R`. The indexed presentation uses only the published families `State`, `Label`, `Neighbourhood`, `Path`, `Transition`, `AutomatonAccepts`; specialized compiler/evaluator operations occur *before* grammar expansion, not in the grammar. Because `EPAL^R = EPAL`, the resulting PEG recognizes all binary even palindromes.

## Constructive existence versus physical grammar

The generator is a mathematically finite object, but its expansion is astronomically large: 295 tapes, scaffold degree 590, input bound `K=416945810716`, block width `B=549755813888`. The release provides the finite indexed enumeration and representative full-machine expansions, not a fully materialized printed grammar. The key proof obligation is that every index domain and transition computation is finite and standard PEG rules are emitted for every index.

## What was checked

- 30 selected July 25 tests for indexed expansion, literal reduced backend, and source/scheduler composition: 0 recorded failures.
- Final digests of the schema and proof/audit certificates are pinned in `AUDIT_STATUS.md`.
- Fresh October 19, 2026 run of `tests/test_indexed_peg_expander.py`: 4 passed.

Tests support the implementation; they are not an exhaustive proof over all strings or a proof assistant's acceptance of every lemma.

## The additional generic theorem

The follow-on audit (`notes/REALTIME_TM_REVERSE_PEG_THEOREM_AUDIT_2026-07-25.md`) extracts an independent claimed theorem: for each deterministic **conventional real-time** multitape TM `M`, there is an effective ordinary PEG for `L(M)^R`. Its proof uses a cell-level zipper scaffold with radius 2; a fixed-bounded-delay block theorem follows similarly. This generic theorem has not received external audit and is **not** the same as the open claim that *every* CFL is PEG-recognizable.

## Key literature

Bruno Loff, Nelma Moreira, Rogério Reis. "The computational power of parsing expression grammars." *Journal of Computer and System Sciences* **111** (2020). DOI: https://doi.org/10.1016/j.jcss.2020.01.001 ; preprint: https://arxiv.org/abs/1902.08272