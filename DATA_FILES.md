# Generated binary tables — six pending upload

The public repository includes the Python source, tests, proof checkpoints, text-based generated proof certificates, and **one** of the seven compressed tables from the July 25, 2026 research archive: `generated/pattern_prepare_ordinary_table.json.gz` (334 bytes; SHA-256 `a8be0619261a03bbf2a58ca0e53f90d386e46a05865cb148f56218a7b2ccda94`).

The **six** tables listed below are still missing from the GitHub tree. They are available byte-for-byte in the archived release ZIP, and their checksums were reconfirmed on October 19, 2026. The tables are generated artifacts, not extra PEG operators. They must not be recreated from guessed fixture contents.

| Missing path | Bytes | SHA-256 |
| --- | ---: | --- |
| `generated/algorithm_y_ordinary_table.json.gz` | 1,259,801 | `e4a177d176cc2c4577dce77a8125af9ec65540e8f477e7b118c9c0a7a0f97dfa` |
| `generated/checkpoint_ordinary_table.json.gz` | 4,253,327 | `2127c2e8c1bcab1f4c7b73a5f2d9cd83859927824b819d090ab543838f435d5e` |
| `generated/checkpoint_reusable_table.json.gz` | 4,257,535 | `0496d1245da39b543f8d6ed3c4073a410e6229f5e1e2cc7b11b49467b8eea0e4` |
| `generated/history_zipper_ordinary_table.json.gz` | 873,013 | `c20ef8439e5a99ed65744ca297735f28546b6245f5b298232ea78088f290676b` |
| `generated/outer_dispatcher_patch.jsonl.gz` | 3,621,426 | `39667353a0fca3b6b00cebbf57978585c0d9d60110ab932e2b252097757f19dd` |
| `generated/outer_service_fabric_body.jsonl.gz` | 35,188,780 | `9d37cd54bd250de8d14209fd209dc733e2a8be314dd3a1c5677f49fe0834e1e8` |

## Importing the missing tables

Extract only the six named files from the original release ZIP into the checkout root (preserving the `generated/` directory), then verify their hashes against this table and commit them. A prepared six-file upload bundle and an accompanying verification/push script are distributed separately with the release handoff.

Use `git push` rather than GitHub's browser file uploader: the largest file is about 35 MB, which exceeds the browser's per-file limit but is below the usual 100 MB Git object limit. Git LFS is not required.

After upload, update this document to record that all tables are present, and rerun the relevant integration tests. The compressed tables are not required for the four fast indexed-expander tests cited in `AUDIT_STATUS.md`.
