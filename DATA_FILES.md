# Generated binary tables — complete as of October 19, 2026

**All seven compressed generated tables are now present on GitHub's `main` branch.** The final six arrived with commit [`13e9707`](https://github.com/abiggerhammer/peg-palindrome-construction/commit/13e970716bdb5693e7fc16d451c175f7ddd5c8bc). The smaller `pattern_prepare` table was already tracked.

The October 19 release verification compared the GitHub tree's **Git blob SHA-1 and byte lengths** for all seven files against the exact archived July 25 release bytes, and independently checked the archived file bytes against the SHA-256 manifest below. All seven comparisons matched. This checks the *identity and completeness of the published data*, not any mathematical theorem or the correctness of a regeneration algorithm.

| Tracked path | Bytes | SHA-256 |
| --- | ---: | --- |
| `generated/algorithm_y_ordinary_table.json.gz` | 1,259,801 | `e4a177d176cc2c4577dce77a8125af9ec65540e8f477e7b118c9c0a7a0f97dfa` |
| `generated/checkpoint_ordinary_table.json.gz` | 4,253,327 | `2127c2e8c1bcab1f4c7b73a5f2d9cd83859927824b819d090ab543838f435d5e` |
| `generated/checkpoint_reusable_table.json.gz` | 4,257,535 | `0496d1245da39b543f8d6ed3c4073a410e6229f5e1e2cc7b11b49467b8eea0e4` |
| `generated/history_zipper_ordinary_table.json.gz` | 873,013 | `c20ef8439e5a99ed65744ca297735f28546b6245f5b298232ea78088f290676b` |
| `generated/outer_dispatcher_patch.jsonl.gz` | 3,621,426 | `39667353a0fca3b6b00cebbf57978585c0d9d60110ab932e2b252097757f19dd` |
| `generated/outer_service_fabric_body.jsonl.gz` | 35,188,780 | `9d37cd54bd250de8d14209fd209dc733e2a8be314dd3a1c5677f49fe0834e1e8` |
| `generated/pattern_prepare_ordinary_table.json.gz` | 334 | `a8be0619261a03bbf2a58ca0e53f90d386e46a05865cb148f56218a7b2ccda94` |

## Verify from a clean clone

The following command validates the compressed bytes currently checked out, independently of Git object metadata:

```bash
sha256sum --check <<'SHA256'
e4a177d176cc2c4577dce77a8125af9ec65540e8f477e7b118c9c0a7a0f97dfa  generated/algorithm_y_ordinary_table.json.gz
2127c2e8c1bcab1f4c7b73a5f2d9cd83859927824b819d090ab543838f435d5e  generated/checkpoint_ordinary_table.json.gz
0496d1245da39b543f8d6ed3c4073a410e6229f5e1e2cc7b11b49467b8eea0e4  generated/checkpoint_reusable_table.json.gz
c20ef8439e5a99ed65744ca297735f28546b6245f5b298232ea78088f290676b  generated/history_zipper_ordinary_table.json.gz
39667353a0fca3b6b00cebbf57978585c0d9d60110ab932e2b252097757f19dd  generated/outer_dispatcher_patch.jsonl.gz
9d37cd54bd250de8d14209fd209dc733e2a8be314dd3a1c5677f49fe0834e1e8  generated/outer_service_fabric_body.jsonl.gz
a8be0619261a03bbf2a58ca0e53f90d386e46a05865cb148f56218a7b2ccda94  generated/pattern_prepare_ordinary_table.json.gz
SHA256
```

These are generated research artifacts, not new PEG operators. No claims are made that the large tables or the astronomical fully expanded PEG are cheap to regenerate or execute. For mathematical status and regression-test limitations, see [AUDIT_STATUS.md](AUDIT_STATUS.md) and [PROOF_OVERVIEW.md](PROOF_OVERVIEW.md).
