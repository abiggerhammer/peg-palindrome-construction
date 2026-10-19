"""Regenerate the proved compact Galil scheduler specification."""

from __future__ import annotations

import json
from pathlib import Path

from predictability_scheduler import compact_scheduler_spec
from scheduler_parameters import certificate_dict, GALIL_PREDICTABILITY_C


def main(path: str | Path = "generated/galil_scheduler_c16.json") -> dict:
    data = compact_scheduler_spec(GALIL_PREDICTABILITY_C)
    data["source_predictability_certificate"] = certificate_dict()
    data["status"] = (
        "predictability translation, compact scheduler parameters, ordinary source composition, "
        "and the fixed Hartmanis--Stearns speedup application are proved"
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
