"""Emit the indexed ordinary PEG presentation for even palindromes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import history_zipper_ordinary_tm as hz
from constant_speedup import MACRO_CAPACITY, SPEEDUP_HALVINGS
from enumerate_scheduled_rows import registered_source_alphabets
from scheduled_source_composition import (
    AWAIT_FAST,
    AWAIT_SLOW,
    BLANK,
    BUFFER_CONTINUATION_TAPE,
    BUFFER_DATA_START,
    BUFFER_REGISTER_TAPE,
    BUFFER_STATES,
    CLOCK_START,
    CLOCK_WIDTH,
    LAG_TAPE,
    MODE_TAPE,
    PENDING_OUTPUT_TAPE,
    SCHEDULED_STATES,
    SCHEDULED_TOTAL_ROWS,
    SCHEDULED_WORK_TAPES,
    SOURCE_Q_START,
    SOURCE_STATE_BITS,
    BOUNDED_DELAY_TRANSITIONS,
)
from succinct_block_peg import (
    AlphabetDescriptor,
    BoundedDelaySpec,
    compile_bounded_delay_to_succinct_peg,
)


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def alphabet_descriptors() -> tuple[AlphabetDescriptor, ...]:
    items: list[AlphabetDescriptor] = []
    # Exact finite cardinality for every source tape.  Large alphabets are not
    # copied into the JSON; the named enumerator returns their literal tuples.
    source_alphabets = registered_source_alphabets()
    for tape, alphabet in enumerate(source_alphabets):
        items.append(
            AlphabetDescriptor(
                tape, tape + 1,
                "certified source-fabric alphabet",
                cardinality=len(alphabet),
                oracle=f"enumerate_scheduled_rows.registered_source_alphabets()[{tape}]",
            )
        )
    # The scheduler input-history data tapes are literal finite alphabets.
    hm = hz.machine()
    for local, alphabet in enumerate(hm.tape_alphabets):
        items.append(
            AlphabetDescriptor(
                BUFFER_DATA_START + local,
                BUFFER_DATA_START + local + 1,
                "literal",
                cardinality=len(alphabet),
                values=tuple(alphabet),
            )
        )
    items.append(
        AlphabetDescriptor(
            BUFFER_REGISTER_TAPE,
            BUFFER_REGISTER_TAPE + 1,
            "history-worker state register",
            cardinality=BUFFER_STATES + 1,
            oracle="enumerate '_' then @SCHED_INPUT:q<i> for 0<=i<BUFFER_STATES",
        )
    )
    items.append(
        AlphabetDescriptor(
            BUFFER_CONTINUATION_TAPE,
            BUFFER_CONTINUATION_TAPE + 1,
            "literal",
            values=(BLANK, "@CONT:q2", "@CONT:q3", "@CONT:q4", "@CONT:q5"),
            cardinality=5,
        )
    )
    for tape in range(SOURCE_Q_START, SOURCE_Q_START + SOURCE_STATE_BITS):
        items.append(AlphabetDescriptor(tape, tape + 1, "literal", 3, (BLANK, 0, 1)))
    for tape in range(CLOCK_START, CLOCK_START + CLOCK_WIDTH):
        items.append(AlphabetDescriptor(tape, tape + 1, "literal", 3, (BLANK, 0, 1)))
    items.append(AlphabetDescriptor(LAG_TAPE, LAG_TAPE + 1, "literal", 3, (BLANK, "#", "1")))
    items.append(AlphabetDescriptor(PENDING_OUTPUT_TAPE, PENDING_OUTPUT_TAPE + 1, "literal", 3, (BLANK, 0, 1)))
    items.append(AlphabetDescriptor(MODE_TAPE, MODE_TAPE + 1, "literal", 3, (BLANK, "F", "S")))
    return tuple(items)


def build_spec() -> BoundedDelaySpec:
    manifest = Path("generated/scheduled_composition_row_family_manifest.json")
    return BoundedDelaySpec(
        name="corrected SG source composed with compact Galil FAST/SLOW scheduler",
        language="{w w^R : w in {0,1}*}",
        input_alphabet=("0", "1"),
        tape_count=SCHEDULED_WORK_TAPES,
        state_count=SCHEDULED_STATES,
        boundary_states=(AWAIT_FAST, AWAIT_SLOW),
        initial_boundary_state=AWAIT_FAST,
        initial_output=1,
        delay_bound=BOUNDED_DELAY_TRANSITIONS,
        macro_capacity=MACRO_CAPACITY,
        squaring_layers=SPEEDUP_HALVINGS,
        sparse_row_count=SCHEDULED_TOTAL_ROWS,
        row_family_manifest=str(manifest),
        row_family_manifest_sha256=_sha256(manifest),
        row_enumerator_entrypoint="enumerate_scheduled_rows.iter_scheduled_rows",
        alphabet_descriptors=alphabet_descriptors(),
        blank_symbol=BLANK,
    )


def main(
    output: str | Path = "generated/palindrome_reverse.speg.json",
    certificate: str | Path = "generated/palindrome_peg_compiler_certificate.json",
) -> dict:
    spec = build_spec()
    grammar = compile_bounded_delay_to_succinct_peg(spec)
    data = grammar.write(output)
    audit_path = Path("generated/palindrome_indexed_rule_audit.json")
    cert = {
        "format": "palindrome finite ordinary-PEG compiler certificate v3",
        "status": grammar.status,
        "grammar_path": str(output),
        "grammar_sha256": grammar.sha256(),
        "definition_audit_path": str(audit_path),
        "definition_audit_sha256": _sha256(audit_path) if audit_path.exists() else None,
        "source_row_family_manifest": spec.row_family_manifest,
        "source_row_family_manifest_sha256": spec.row_family_manifest_sha256,
        "row_enumerator_entrypoint": spec.row_enumerator_entrypoint,
        "block_size": spec.macro_capacity,
        "delay_bound": spec.delay_bound,
        "optional_squaring_layers": spec.squaring_layers,
        "scaffold_degree": grammar.scaffold_degree,
        "scaffold_radius": grammar.scaffold_radius,
        "state_predicates": grammar.state_predicates,
        "path_predicates": grammar.path_predicates,
        "minimum_indexed_block_cell_coordinates": 3 * spec.tape_count * spec.macro_capacity,
        "compiler_entrypoint": "compile_palindrome_succinct_peg.main",
        "ordinary_rule_expanders": [
            "indexed_block_macro_expander",
            "lmr_rule_expander",
        ],
        "small_instance_literal_backend": "bounded_delay_macro_compiler.compile_small_bounded_delay_to_peg",
        "claim_boundary": {
            "proved_within_construction": [
                "finite exact working-label and radius-two neighbourhood domains",
                "unique nonreentered synthetic initial state",
                "total scaffolding delta via explicit rejecting sink completion",
                "block locality and radius-two persistent update",
                "finite compile-time ordinary-row transition oracle",
                "line-for-line standard LMR State/Label/Neighbourhood/Path/Transition expansion",
                "literal ordinary-PEG correctness on reduced bounded-delay machines",
                "existence of a finite ordinary PEG for even palindromes",
            ],
            "not_claimed": [
                "physical materialization of the astronomical ordinary PEG text",
                "practical completion time for exhaustive expansion",
                "independent external verification or publication-level acceptance",
            ],
        },
    }
    path = Path(certificate)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cert, indent=2, sort_keys=True) + "\n")
    print(json.dumps(cert, indent=2, sort_keys=True))
    return {"grammar": data, "certificate": cert}


if __name__ == "__main__":
    main()
