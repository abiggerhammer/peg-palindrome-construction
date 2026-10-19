"""Final LMR-definition audit and selected full-machine rule expansion."""

from __future__ import annotations

import json
from pathlib import Path

from case14_predictability_bounds import case3_at_end_bound
from compile_palindrome_succinct_peg import build_spec
from indexed_block_macro_expander import (
    INITIAL_STATE,
    TransitionIndex,
    base_neighbourhood,
    fixed_full_rules,
    neighbourhood_plan,
    normal_state,
    state_contribution_from_values,
    transition_plan,
)
from scheduled_source_composition import (
    AWAIT_FAST,
    CLOCK_START,
    CLOCK_WIDTH,
    LAG_BOTTOM,
    LAG_TAPE,
    MODE_FAST,
    MODE_TAPE,
    PENDING_OUTPUT_TAPE,
    SOURCE_DONE_0,
    SOURCE_Q_START,
    SOURCE_STATE_BITS,
    _bits_le,
)
from scheduler_parameters import GALIL_PREDICTABILITY_C, GALIL_SCHEDULER_PERIOD
from sg_outer_incremental import OrdinarySGOuterIncremental
from sg_zero_ratio import UpdateCase
from succinct_block_peg import compile_bounded_delay_to_succinct_peg

INITIAL_CASE3_BOUND = case3_at_end_bound(1)


def _initial_semantic_witness(symbol: str) -> dict:
    source = OrdinarySGOuterIncremental(audit=True, background_work_budget=8)
    record = source.append(symbol)
    if record.output:
        raise AssertionError("a one-symbol word is not an even palindrome")
    if record.case is not UpdateCase.THREE_SECOND_SURVIVES:
        raise AssertionError(record.case)
    if INITIAL_CASE3_BOUND >= GALIL_PREDICTABILITY_C:
        raise AssertionError((INITIAL_CASE3_BOUND, GALIL_PREDICTABILITY_C))
    return {
        "input_symbol": symbol,
        "source_case": record.case.name,
        "source_output": 0,
        "proved_source_bound": INITIAL_CASE3_BOUND,
        "scheduler_c": GALIL_PREDICTABILITY_C,
        "scheduler_consequence": (
            "the source interval completes before the first speculative clock tick; "
            "the simulated and physical input heads remain equal"
        ),
        "next_normal_state": list(normal_state(AWAIT_FAST, 0)),
        "next_output": 0,
        "evidence_class": (
            "semantic source execution plus proved primitive upper bound; the complete "
            "8,305,403-row interval was not replayed in this audit"
        ),
    }


def _scheduler_projection() -> dict:
    return {
        "source_state_register_little_endian": list(_bits_le(SOURCE_DONE_0, SOURCE_STATE_BITS)),
        "clock_register_little_endian": list(_bits_le(GALIL_SCHEDULER_PERIOD, CLOCK_WIDTH)),
        "lag_tape_cell_zero": LAG_BOTTOM,
        "pending_output_tape_cell_zero": 0,
        "mode_tape_cell_zero": MODE_FAST,
        "head_offsets": {
            "source_state_bits": {"start_tape": SOURCE_Q_START, "value": 0},
            "clock_bits": {"start_tape": CLOCK_START, "value": 0},
            "lag": {"tape": LAG_TAPE, "value": 0},
            "pending_output": {"tape": PENDING_OUTPUT_TAPE, "value": 0},
            "mode": {"tape": MODE_TAPE, "value": 0},
        },
        "meaning": (
            "selected coordinates of the exact whole canonical label emitted by the "
            "compile-time transition oracle"
        ),
    }


def main(
    audit_path: str | Path = "generated/palindrome_indexed_rule_audit.json",
    text_path: str | Path = "PALINDROME_INDEXED_PEG_AUDIT_2026-07-25.md",
) -> dict:
    spec = build_spec()
    grammar = compile_bounded_delay_to_succinct_peg(spec)
    degree = grammar.scaffold_degree
    base = base_neighbourhood(degree)
    fixed = fixed_full_rules(
        degree=degree,
        initial_output=spec.initial_output,
        boundary_states=spec.boundary_states,
    )

    selected = []
    for symbol in spec.input_alphabet:
        index = TransitionIndex(INITIAL_STATE, symbol, base)
        selected.append({
            "index": {
                "old_state": "INITIAL",
                "input_symbol": symbol,
                "neighbourhood": "trivial unlabelled radius-two base tree",
                "id": index.id(),
            },
            "neighbourhood_rule": neighbourhood_plan(base),
            "transition_rule": transition_plan(index),
            "state_alternative": state_contribution_from_values(
                index, next_boundary_state=AWAIT_FAST, output=0
            ),
            "whole_label_projection": _scheduler_projection(),
            "semantic_witness": _initial_semantic_witness(symbol),
        })

    data = {
        "format": "palindrome indexed PEG definition audit v2",
        "status": (
            "standard LMR finite-abbreviation theorem discharged within the construction"
        ),
        "paper_correspondence": {
            "State": "LMR State(q)",
            "Label": "LMR Label(gamma), with gamma an exact whole tagged block label",
            "Neighbourhood": "LMR Neighbourhood(N) over the full finite N_2(d,Gamma) domain",
            "Path": "LMR Path(p) for p in [d]^{<=2}",
            "Transition": "&(sigma State(q)) &(sigma Neighbourhood(N))",
            "AutomatonAccepts": "choice of accepting State rules followed by ANY*",
            "unique_initial_state": (
                "a synthetic INITIAL state is used only at the unlabelled base and is "
                "never an outcome of delta"
            ),
        },
        "finite_expansion": {
            "schema_version": grammar.version,
            "state_count": grammar.state_predicates,
            "degree": grammar.scaffold_degree,
            "radius": grammar.scaffold_radius,
            "path_rule_count": grammar.path_predicates,
            "domain_constructors": [
                "finite enum", "finite range", "finite sum", "finite product",
                "fixed-length vector over a finite alphabet",
            ],
            "row_enumerator": spec.row_enumerator_entrypoint,
            "row_count": spec.sparse_row_count,
            "per_transition_simulation_bound": spec.delay_bound,
            "ordinary_expanders": [
                "indexed_block_macro_expander",
                "lmr_rule_expander",
            ],
            "macro_gate_is_not_a_peg_operator": True,
            "totality": (
                "all noncanonical or otherwise unreachable exact neighbourhoods are sent "
                "to the explicit rejecting SINK state and SINK_LABEL"
            ),
        },
        "fixed_ordinary_rules": fixed,
        "selected_full_machine_expansions": selected,
        "theorem": {
            "statement": (
                "Exhausting the stated finite loops prints a finite ordinary PEG for the "
                "reverse of the language decided by the bounded-delay palindrome machine."
            ),
            "reversal_step": (
                "the even-palindrome language is invariant under reversal, so the same PEG "
                "recognises even palindromes"
            ),
            "claim_class": "proved within the checked construction, pending independent review",
        },
    }

    audit_path = Path(audit_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    lines = [
        "# Indexed ordinary-PEG definition audit",
        "",
        "Date: 2026-07-25",
        "",
        "## Result",
        "",
        "The full presentation is now an exact finite abbreviation of the ordinary",
        "Loff--Moreira--Reis sufficient-direction grammar. It has only the standard",
        "families `State`, `Label`, `Neighbourhood`, `Path`, `Transition`, and",
        "`AutomatonAccepts`. Bounded-delay simulation is compile-time work and does",
        "not occur as a PEG operator.",
        "",
        "A synthetic `INITIAL` state is used only on the unlabelled base. Normal",
        "states are `(boundary_state, output_bit)`, and a rejecting `SINK` completes",
        "the transition function on every noncanonical member of the full finite",
        "radius-two neighbourhood domain.",
        "",
        "## Line-by-line correspondence",
        "",
        "| LMR item | Indexed family |",
        "|---|---|",
        "| `State(q)` | `State[state]` |",
        "| `Label(gamma)` | `Label[whole tagged block label]` |",
        "| `Neighbourhood(N)` | `Neighbourhood[exact N_2 tree]` |",
        "| `Path(p)` | `Path[path of length at most 2]` |",
        "| `Transition(q,sigma,N)` | `&(sigma State(q)) &(sigma Neighbourhood(N))` |",
        "| accepting rule | accepting states followed by `.*` |",
        "",
        "The exact neighbourhood rule checks the root label, every present path,",
        "the exact label at each present path, and every missing path. This is the",
        "published construction rather than a new grammar operator.",
        "",
        "## Selected full-machine rules",
        "",
        "`Path_eps <- epsilon`",
        "",
        "`State_INITIAL <- EOF`",
        "",
        "The trivial unlabelled radius-two base neighbourhood also has the sole",
        "alternative `EOF`.",
    ]
    for item in selected:
        tr = item["transition_rule"]
        state = item["state_alternative"]
        symbol = item["index"]["input_symbol"]
        lines.extend((
            "",
            f"### First physical symbol `{symbol}`",
            "",
            f"`{tr['lhs']} <- &('{symbol}' State_INITIAL) "
            f"&('{symbol}' {item['neighbourhood_rule']['lhs']})`",
            "",
            f"This adds `{state['body']['name']}` as an alternative of `{state['lhs']}`.",
            f"The source branch is initial case 3 and has proved cost at most "
            f"{INITIAL_CASE3_BOUND}, below scheduler c={GALIL_PREDICTABILITY_C};",
            "there is no speculative tick, the emitted bit is 0, and the next normal",
            "scheduler state is `(AWAIT_FAST,0)`.",
        ))
    lines.extend((
        "",
        "## Finiteness and termination",
        "",
        "Every work-tape alphabet is finite. The block width, tape count, state set,",
        "degree, and radius are fixed integers. Therefore the whole-label alphabet,",
        "the recursively defined radius-two neighbourhood set, the path set, and the",
        "transition-index set are finite.",
        "",
        f"For each transition index, the compiler scans the finite {spec.sparse_row_count}-row",
        f"ordinary machine for at most {spec.delay_bound} primitive steps. It then emits",
        "one finite scaffolding transition and folds it into the standard ordinary PEG",
        "alternatives. Noncanonical indices take the constant rejecting sink transition.",
        "Thus the nested generator terminates and prints a finite ordinary PEG.",
        "",
        "## Claim boundary",
        "",
        "The astronomical grammar text has not been physically printed. The finite domains,",
        "total transition algorithm, standard rule templates, and selected concrete rules",
        "are explicit and executable. The theorem is classified as proved within this",
        "construction, not as independently reviewed or published.",
    ))
    Path(text_path).write_text("\n".join(lines) + "\n")
    return data


if __name__ == "__main__":
    main()
