# Binary even palindromes in an ordinary PEG — constructive proof candidate

**Status: research release for independent audit. Not peer reviewed or proof-assistant checked.**

**New to the problem? Start with [EXPLAINER.md](EXPLAINER.md).** It explains why an even-palindrome CFG is trivial but an ordinary PEG is not, why Conjecture 7 matters, and exactly what this construction claims and still needs reviewed. No knowledge of scaffolding automata is assumed.

This repository documents a July 25, 2026 AI-assisted construction, developed under the direction of **Meredith L. Patterson** with OpenAI's Sol, that purports to establish the existence of a **finite ordinary parsing expression grammar (PEG)** for the complete language of binary even-length palindromes:

```text
EPAL = { w reverse(w) : w in {0,1}* }.
```

This would refute **Conjecture 7** of Bruno Loff, Nelma Moreira, and Rogério Reis, *The Computational Power of Parsing Expression Grammars*, Journal of Computer and System Sciences **111** (2020), DOI: [10.1016/j.jcss.2020.01.001](https://doi.org/10.1016/j.jcss.2020.01.001). The authors constructed a PEG for palindromes of restricted lengths and conjectured that even-length binary palindromes have no PEG.

**This is a proposed counterexample, not an independently accepted resolution.** Please look for gaps, especially in the source-machine correctness argument, bounded-delay schedule, totality/initial-state conditions, and finite expansion into standard PEG syntax.

## Claim

There is an effectively specified finite **ordinary** PEG `G` such that

```text
L(G) = { w reverse(w) : w in {0,1}* }.
```

"Ordinary" means that after finite expansion the grammar uses terminals, nonterminals, epsilon, sequence, ordered choice, syntactic and-/not-predicates, and repetition. It has no embedded Turing-machine evaluator or special-purpose palindrome primitive. **The fully expanded grammar has not been printed**: it is astronomically large, so this repository supplies an indexed, effectively finite generation specification plus selected concrete expansions and regression tests.

## Construction at a glance

```text
Seiferas–Galil even-palindrome online recognizer
       ↓  corrected six-case controller and checkpoint invariants
Galil FAST/SLOW scheduling and fixed-delay bounds
       ↓  K = 416,945,810,716 primitive steps / input symbol
Deterministic fixed-bounded-delay multitape machine
       ↓  aligned blocks of B = 2^39 cells, persistent stack/zipper representation
Finite total radius-2 scaffolding automaton
       ↓  Loff–Moreira–Reis scaffolding-to-PEG rule families
Finite ordinary PEG for reverse(EPAL) = EPAL
```

The configured machine has 295 work tapes and 1,653,051 states; the scaffold degree is 590. Those figures are properties of the explicit construction, not practical parsing recommendations.

## What to read

1. **[EXPLAINER.md](EXPLAINER.md)** — start here if you're new to CFGs versus PEGs, or want the intuition before the technical proof.
2. **[PROOF_OVERVIEW.md](PROOF_OVERVIEW.md)** — human-readable dependency graph and theorem boundary.
3. **[PALINDROME_PEG_EXISTENCE_CHECKPOINT_2026-07-25.md](PALINDROME_PEG_EXISTENCE_CHECKPOINT_2026-07-25.md)** — final existence checkpoint with formal finiteness and the rule-expansion argument.
4. **[PALINDROME_INDEXED_PEG_AUDIT_2026-07-25.md](PALINDROME_INDEXED_PEG_AUDIT_2026-07-25.md)** — correspondence with the standard Loff–Moreira–Reis construction.
5. **[CHECKPOINT_CORRECT_PROOF_2026-07-25.md](CHECKPOINT_CORRECT_PROOF_2026-07-25.md)**, **[SIX_CASE_PREDICTABILITY_THEOREM_2026-07-25.md](SIX_CASE_PREDICTABILITY_THEOREM_2026-07-25.md)**, and **[SCHEDULER_SOURCE_COMPOSITION_PROOF_2026-07-25.md](SCHEDULER_SOURCE_COMPOSITION_PROOF_2026-07-25.md)** — source and scheduler dependencies.
6. **[notes/REALTIME_TM_REVERSE_PEG_THEOREM_AUDIT_2026-07-25.md](notes/REALTIME_TM_REVERSE_PEG_THEOREM_AUDIT_2026-07-25.md)** — separate, unreviewed generic theorem proposed by the same work.

The generator entry point is [`compile_palindrome_succinct_peg.py`](compile_palindrome_succinct_peg.py), the indexed PEG schema is [`generated/palindrome_reverse.speg.json`](generated/palindrome_reverse.speg.json), and rule-expansion code is in [`indexed_block_macro_expander.py`](indexed_block_macro_expander.py) and [`lmr_rule_expander.py`](lmr_rule_expander.py).

## Evidence and limitations

- The July 25 checkpoint records **30 selected tests passed**, along with deterministic generation and SHA-256 values for the final artifacts.
- The indexed construction explicitly repairs two discovered formal defects: reuse of the initial state, and a transition function that had been specified only for canonical reachable neighbourhoods instead of **all** finite formal neighbourhoods.
- Small-instance PEG/machine differential tests exercise the generic compiler, but do **not** execute the astronomically large final PEG.
- No independent mathematical audit, peer review, or Lean/Rocq proof has been completed. "Certificate" in artifact names refers to project-generated consistency/derivation records, **not** proof-assistant certification.
- The associated generic audit identifies a small literal-helper second-block field that needs clarification or repair; see its **Needs rechecking** section.

## Basic validation

```bash
python tools/verify_release_artifacts.py
python -m pytest -q tests/test_indexed_peg_expander.py
```

The verifier checks SHA-256 against the pinned July 25 release for all seven generated compressed tables, the final indexed schema, two certificates, and the proof audit document. The four indexed-expander tests and three further targeted scheduler/compiler tests passed in an October 19, 2026 rerun. The [release integrity GitHub Actions workflow](.github/workflows/release-integrity.yml) reproduces this bounded subset on a clean checkout; it is not a full test-suite or mathematical proof check. Some tests can be slow; historical results are recorded in `*_TEST_RESULTS_2026-07-25.txt`. See [AUDIT_STATUS.md](AUDIT_STATUS.md) for the precise scope and limitations.

## What we want reviewed

- Does the specialized source recognizer decide **all and only** binary even palindromes under the stated input/output convention?
- Are the quantitative availability, predictability and FAST/SLOW claims sufficient to yield a fixed bounded delay independent of input length?
- Does the persistent block construction correctly encode every reachable boundary configuration using only radius-2 paths? Are its malformed neighbourhood transitions total?
- Does the finitely indexed rule specification expand *exactly* to a standard PEG under the published Loff–Moreira–Reis sufficient-direction construction, including empty input and EOF semantics?

Please report counterexamples or missing assumptions with the relevant file and lemma. The publication priority is **independent audit**, not claims of a fully machine-verified theorem.

## Provenance and reuse

The underlying research workbench was recovered from the Library's July 25 Git bundle at original commit `be2bc10d2d8661b8e3d8ba2dab664c3c43150b71`. The current GitHub import preserves the code and text-based certificates. All seven compressed generated tables are now published in GitHub and match the archived release byte-for-byte; see the full SHA-256 manifest and clean-clone verification command in [`DATA_FILES.md`](DATA_FILES.md). The public-facing README and supplemental notes have been added separately. The earlier workbench README is in [`notes/ORIGINAL_WORKBENCH_README_2026-07-25.md`](notes/ORIGINAL_WORKBENCH_README_2026-07-25.md).

**License:** Code, tests, and generated artifacts: [Apache-2.0](LICENSE). Original proof documentation and research exposition: [CC BY 4.0](LICENSE-DOCS.md), except third-party material, which retains its own license and attribution. **Authorship:** AI-assisted research and tooling, with human research direction; the details are recorded here to avoid suggesting the proof was produced entirely by a human.
