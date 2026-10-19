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

## Before making strong academic claims

Seek independent review of the Seiferas–Galil specialization and its correctness; validate scheduling and the quantitative bounds; separately audit the scaffold-to-ordinary-PEG expansion against the Loff–Moreira–Reis characterization; check the empty input and acceptance conventions; and make test commands, dependencies, and a minimal reproducibility case easy for reviewers to run. Submit a full written proof to a peer-reviewed venue after that.