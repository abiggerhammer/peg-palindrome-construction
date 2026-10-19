# Generated binary tables (pending upload)

The public repository currently contains the Python source, tests, written proof checkpoints, and text-based generated proof certificates. The seven compressed generated tables listed below are part of the original July 25 research archive but are **not yet included in the GitHub tree**. Some regeneration and integration tests may require these files.

All seven files are in the complete local release ZIP delivered with this project. After extracting that ZIP at the repository root, they can be added with `git add generated/*.gz` and pushed normally. This document should be updated or removed once they are in GitHub.

| Path | Bytes | SHA-256 |
| --- | ---: | --- |
| `generated/algorithm_y_ordinary_table.json.gz` | 1,259,801 | `e4a177d176cc2c4577dce77a8125af9ec65540e8f477e7b118c9c0a7a0f97dfa` |
| `generated/checkpoint_ordinary_table.json.gz` | 4,253,327 | `2127c2e8c1bcab1f4c7b73a5f2d9cd83859927824b819d090ab543838f435d5e` |
| `generated/checkpoint_reusable_table.json.gz` | 4,257,535 | `0496d1245da39b543f8d6ed3c4073a410e6229f5e1e2cc7b11b49467b8eea0e4` |
| `generated/history_zipper_ordinary_table.json.gz` | 873,013 | `c20ef8439e5a99ed65744ca297735f28546b6245f5b298232ea78088f290676b` |
| `generated/outer_dispatcher_patch.jsonl.gz` | 3,621,426 | `39667353a0fca3b6b00cebbf57978585c0d9d60110ab932e2b252097757f19dd` |
| `generated/outer_service_fabric_body.jsonl.gz` | 35,188,780 | `9d37cd54bd250de8d14209fd209dc733e2a8be314dd3a1c5677f49fe0834e1e8` |
| `generated/pattern_prepare_ordinary_table.json.gz` | 334 | `a8be0619261a03bbf2a58ca0e53f90d386e46a05865cb148f56218a7b2ccda94` |

These are generated artifacts, not new PEG operators. Their byte content is intentionally not reconstructed from test fixtures or guessed values.
