# Audit status and provenance — 2026-10-19

**Status:** candidate constructive mathematical result, internally checked, not independently reviewed, peer-reviewed, or proof-assistant checked.

## Core claim and caveats

The proposed PEG is *ordinary* upon full expansion, finite by enumerated bounded constructions, and recognizes `{ww^R : w∈{0,1}*}` if each linked lemma is correct. The physical grammar is not printed and would be infeasible to expand in practice. The documented program is not a practical palindrome parser.

The indexed PEG audit previously found and repaired (a) a re-enterable initial state, and (b) missing totalization of the transition on all formal radius-two neighborhoods. Subsequent independent verification is still required.

The follow-on generic audit also flags a returned, apparently unused second-block field in the small literal block simulator. That helper should be repaired or clarified before making claims about standalone full next-boundary snapshots.

## Hashes from the original checkpoint — verified against restored bundle

```text
7e3f7cab9af2c53b679b8da3ac486c6993824a939c4d689f3e37f9718c20f8f9  generated/palindrome_reverse.speg.json
b3d5281635ff12e85d4b3f30f3b3e38bfb3a4749ddd6339ca9f815cbe40fc089  generated/palindrome_peg_compiler_certificate.json
215894eb65e4544401304b6747e9fa5d97134a96ad9709e467c77064207b056e  generated/palindrome_indexed_rule_audit.json
ad6851b1aff201a31b530a8073b075ead54ac798931b26872e559bb90f66e2fc  PALINDROME_INDEXED_PEG_AUDIT_2026-07-25.md
```

The original workbench commit was `be2bc10d2d8661b8e3d8ba2dab664c3c43150b71`.

## Reproduction guidance

`python -m pytest -q tests/test_indexed_peg_expander.py` reran successfully (4 passed) on October 19, 2026. The entire test suite has **not** been freshly rerun in this packaging pass. A partial broader run reached six passing tests but exceeded a 45-second execution limit; this is not counted as full-suite validation. The historical `PALINDROME_INDEXED_PEG_TEST_RESULTS_2026-07-25.txt` records 30 selected tests passed in July.

Do not interpret the project's JSON 'certificates' as proof-assistant certificates, and do not infer full-grammar materialization from tests on reduced machines.

## GitHub completeness and targeted verification (October 19, 2026)

- All seven archived compressed tables are now published in `main`, the final six in GitHub commit [`13e9707`](https://github.com/abiggerhammer/peg-palindrome-construction/commit/13e970716bdb5693e7fc16d451c175f7ddd5c8bc). Their Git blob SHA-1 identifiers and byte lengths match the original July 25 archive, whose SHA-256 hashes match [DATA_FILES.md](DATA_FILES.md).
- The Python schema, two machine-readable certificates, and the final indexed audit proof document also match the pinned archive SHA-256 values.
- From the restored release archive on Python 3.13.5 / pytest 9.0.2, seven targeted tests passed: four in `tests/test_indexed_peg_expander.py`, plus the public composition constants, source state-bit updates, and sparse-compiler differing-tape-alphabet tests. The six central source/test modules used by the expander test were additionally matched by Git blob SHA-1 against GitHub.
- An attempted broader six-module selection was incomplete after four passing tests and a 105-second execution limit. This was a **timeout, not a failure or a complete passing suite**. Some remaining tests have substantial resource costs.
- `python tools/verify_release_artifacts.py` is the archive integrity command. The [release integrity workflow](.github/workflows/release-integrity.yml) runs this check plus the targeted tests on a GitHub-hosted clean checkout. CI execution is distinct from, and does not replace, mathematical peer review.

## Before making strong academic claims

Seek independent review of the Seiferas–Galil specialization and its correctness; validate scheduling and the quantitative bounds; separately audit the scaffold-to-ordinary-PEG expansion against the Loff–Moreira–Reis characterization; check the empty input and acceptance conventions; and make test commands, dependencies, and a minimal reproducibility case easy for reviewers to run. Submit a full written proof to a peer-reviewed venue after that.