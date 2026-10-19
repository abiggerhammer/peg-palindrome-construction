#!/usr/bin/env python3
"""Verify pinned July 25, 2026 release artifacts by SHA-256.

Checks published compressed table bytes and the three final machine-readable
certificate/schema artifacts. This is an integrity check, not a proof checker.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Exact byte digests from the archived July 25 research release.
EXPECTED = {
    "generated/algorithm_y_ordinary_table.json.gz": "e4a177d176cc2c4577dce77a8125af9ec65540e8f477e7b118c9c0a7a0f97dfa",
    "generated/checkpoint_ordinary_table.json.gz": "2127c2e8c1bcab1f4c7b73a5f2d9cd83859927824b819d090ab543838f435d5e",
    "generated/checkpoint_reusable_table.json.gz": "0496d1245da39b543f8d6ed3c4073a410e6229f5e1e2cc7b11b49467b8eea0e4",
    "generated/history_zipper_ordinary_table.json.gz": "c20ef8439e5a99ed65744ca297735f28546b6245f5b298232ea78088f290676b",
    "generated/outer_dispatcher_patch.jsonl.gz": "39667353a0fca3b6b00cebbf57978585c0d9d60110ab932e2b252097757f19dd",
    "generated/outer_service_fabric_body.jsonl.gz": "9d37cd54bd250de8d14209fd209dc733e2a8be314dd3a1c5677f49fe0834e1e8",
    "generated/pattern_prepare_ordinary_table.json.gz": "a8be0619261a03bbf2a58ca0e53f90d386e46a05865cb148f56218a7b2ccda94",
    "generated/palindrome_reverse.speg.json": "7e3f7cab9af2c53b679b8da3ac486c6993824a939c4d689f3e37f9718c20f8f9",
    "generated/palindrome_peg_compiler_certificate.json": "b3d5281635ff12e85d4b3f30f3b3e38bfb3a4749ddd6339ca9f815cbe40fc089",
    "generated/palindrome_indexed_rule_audit.json": "215894eb65e4544401304b6747e9fa5d97134a96ad9709e467c77064207b056e",
    "PALINDROME_INDEXED_PEG_AUDIT_2026-07-25.md": "ad6851b1aff201a31b530a8073b075ead54ac798931b26872e559bb90f66e2fc",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    failed = []
    for relative, expected in EXPECTED.items():
        path = ROOT / relative
        if not path.is_file():
            print(f"MISSING {relative}")
            failed.append(relative)
            continue
        if sha256_file(path) != expected:
            print(f"MISMATCH {relative}")
            failed.append(relative)
            continue
        print(f"OK {relative}")
    print(f"{len(EXPECTED) - len(failed)}/{len(EXPECTED)} pinned artifacts verified")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
