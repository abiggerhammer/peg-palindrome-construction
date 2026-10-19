"""Finite indexed ordinary-PEG presentations for bounded-delay machines.

A bounded-delay ordinary multitape machine can be compiled directly to a
radius-two scaffolding automaton by storing aligned tape blocks in each
scaffold label.  Applying the sufficient direction of Loff--Moreira--Reis
Theorem 16 then gives an ordinary PEG for the reverse language.

For the palindrome machine the constants are enormous, so this module records
the *finite loops which print that ordinary PEG*.  It is not a new recognition
formalism: ``indexed_block_macro_expander`` gives the on-demand expander, and
expanding every finite domain yields only standard PEG operators.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class AlphabetDescriptor:
    tape_start: int
    tape_end_exclusive: int
    kind: str
    cardinality: int | None = None
    values: tuple[Any, ...] = ()
    oracle: str | None = None

    def validate(self, tape_count: int) -> None:
        if not (0 <= self.tape_start < self.tape_end_exclusive <= tape_count):
            raise ValueError(self)
        if self.cardinality is not None and self.cardinality < 1:
            raise ValueError(self.cardinality)
        if self.values and self.cardinality not in (None, len(self.values)):
            raise ValueError((self.cardinality, self.values))
        if self.cardinality is None:
            raise ValueError(
                "the final indexed PEG needs an explicit finite alphabet cardinality"
            )
        if not self.values and self.oracle is None:
            raise ValueError("nonliteral alphabet needs a finite symbol enumerator")


@dataclass(frozen=True)
class BoundedDelaySpec:
    name: str
    language: str
    input_alphabet: tuple[str, ...]
    tape_count: int
    state_count: int
    boundary_states: tuple[int, ...]
    initial_boundary_state: int
    initial_output: int
    delay_bound: int
    macro_capacity: int
    squaring_layers: int
    sparse_row_count: int
    row_family_manifest: str
    row_family_manifest_sha256: str
    row_enumerator_entrypoint: str
    alphabet_descriptors: tuple[AlphabetDescriptor, ...]
    blank_symbol: str = "_"

    def validate(self) -> None:
        if self.tape_count < 1 or self.state_count < 1:
            raise ValueError("empty machine")
        if self.delay_bound < 1:
            raise ValueError("delay must be positive")
        if self.macro_capacity != 1 << self.squaring_layers:
            raise ValueError("macro capacity must be a power-of-two block width")
        if self.macro_capacity < self.delay_bound:
            raise ValueError("block width is below the certified delay")
        if self.initial_boundary_state not in self.boundary_states:
            raise ValueError("initial state is not a boundary")
        if self.initial_output not in (0, 1):
            raise ValueError("output must be a bit")
        if not self.row_enumerator_entrypoint:
            raise ValueError("missing ordinary-row enumerator")
        covered = [False] * self.tape_count
        for descriptor in self.alphabet_descriptors:
            descriptor.validate(self.tape_count)
            for tape in range(descriptor.tape_start, descriptor.tape_end_exclusive):
                if covered[tape]:
                    raise ValueError(("overlapping alphabet descriptors", tape))
                covered[tape] = True
        if not all(covered):
            raise ValueError(("uncovered tapes", [i for i, value in enumerate(covered) if not value]))


@dataclass(frozen=True)
class RuleFamily:
    name: str
    lhs_domain: Mapping[str, Any]
    alternatives: tuple[Mapping[str, Any], ...]
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class SuccinctPEG:
    format: str
    version: int
    start_rule: str
    recognizes: str
    terminal_direction: str
    scaffold_degree: int
    scaffold_radius: int
    block_size: int
    state_predicates: int
    path_predicates: int
    finite_domains: Mapping[str, Any]
    rule_families: tuple[RuleFamily, ...]
    compile_time_transition_oracle: Mapping[str, Any]
    expansion_algorithm: Mapping[str, Any]
    source_spec: Mapping[str, Any]
    proof_obligations: Mapping[str, str]
    status: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rule_families"] = [asdict(family) for family in self.rule_families]
        return data

    def canonical_bytes(self) -> bytes:
        return (json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode()

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def write(self, path: str | Path) -> dict[str, Any]:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        data["sha256_without_embedded_digest"] = self.sha256()
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        return data


def _range(stop: int, start: int = 0) -> dict[str, Any]:
    return {"kind": "integer_range", "start": start, "stop_exclusive": stop}


def _enum(values) -> dict[str, Any]:
    return {"kind": "explicit_enum", "values": list(values)}


def _power(base: Any, exponent: int) -> dict[str, Any]:
    return {"kind": "finite_vector_domain", "alphabet": base, "length": exponent}


def compile_bounded_delay_to_succinct_peg(spec: BoundedDelaySpec) -> SuccinctPEG:
    """Describe the exact finite ordinary-PEG generation loops.

    Version 3 follows the sufficient direction of Loff--Moreira--Reis
    Theorem 16 literally.  The full finite domains contain ordinary ``State``,
    whole ``Label``, exact ``Neighbourhood``, ``Path``, and ``Transition``
    indices.  Bounded-delay machine simulation happens only in the compiler
    which computes the finite scaffolding transition table.
    """

    spec.validate()
    degree = 2 * spec.tape_count
    radius = 2
    path_predicates = 1 + degree + degree * degree
    normal_states = len(spec.boundary_states) * 2
    state_predicates = 1 + normal_states + 1  # unique INITIAL and rejecting SINK

    tape_alphabets = []
    for descriptor in spec.alphabet_descriptors:
        for tape in range(descriptor.tape_start, descriptor.tape_end_exclusive):
            tape_alphabets.append({
                "tape": tape,
                "cardinality": descriptor.cardinality,
                "values": list(descriptor.values),
                "enumerator": descriptor.oracle,
                "kind": descriptor.kind,
            })
    tape_alphabets.sort(key=lambda item: item["tape"])

    finite_domains = {
        "InputSymbol": _enum(spec.input_alphabet),
        "BoundaryState": _enum(spec.boundary_states),
        "OutputBit": _enum((0, 1)),
        "NormalState": {
            "kind": "finite_product",
            "factors": ["BoundaryState", "OutputBit"],
            "cardinality": normal_states,
        },
        "State": {
            "kind": "finite_disjoint_union",
            "members": [
                {"kind": "singleton", "value": "INITIAL"},
                "NormalState",
                {"kind": "singleton", "value": "SINK"},
            ],
            "cardinality": state_predicates,
        },
        "Tape": _range(spec.tape_count),
        "Edge": _range(degree),
        "PathAtMost2": {
            "kind": "finite_union",
            "members": [
                {"kind": "singleton", "value": []},
                {"kind": "vectors", "alphabet": "Edge", "length": 1},
                {"kind": "vectors", "alphabet": "Edge", "length": 2},
            ],
            "cardinality": path_predicates,
        },
        "BlockOffset": _range(spec.macro_capacity),
        "TapeAlphabet": tape_alphabets,
        "Block(t)": {
            "kind": "dependent_finite_vector",
            "for_each": "t in Tape",
            "domain": _power("TapeAlphabet(t)", spec.macro_capacity),
        },
        "OptionalBlock(t)": {
            "kind": "finite_union",
            "members": [
                {"kind": "singleton", "value": "EMPTY"},
                "Block(t)",
            ],
        },
        "CanonicalTapeLabel(t)": {
            "kind": "finite_product",
            "factors": [
                "BlockOffset", "Block(t)", "OptionalBlock(t)", "OptionalBlock(t)"
            ],
            "meaning": "head offset, current block, left top, right top",
        },
        "CanonicalLabel": {
            "kind": "dependent_finite_product",
            "factors": [
                "OutputBit",
                "CanonicalTapeLabel(t) for every t in Tape",
            ],
        },
        "WorkingLabel": {
            "kind": "finite_disjoint_union",
            "members": [
                "CanonicalLabel",
                {"kind": "singleton", "value": "SINK_LABEL"},
            ],
        },
        "LabelOrUnlabelled": {
            "kind": "finite_union",
            "members": [
                "WorkingLabel",
                {"kind": "singleton", "value": "UNLABELLED"},
            ],
        },
        "Neighbourhood0": "LabelOrUnlabelled",
        "OptionalNeighbourhood0": {
            "kind": "finite_union",
            "members": [
                {"kind": "singleton", "value": "MISSING"},
                "Neighbourhood0",
            ],
        },
        "Neighbourhood1": {
            "kind": "finite_product",
            "factors": [
                "LabelOrUnlabelled",
                {"kind": "vectors", "alphabet": "OptionalNeighbourhood0", "length": degree},
            ],
        },
        "OptionalNeighbourhood1": {
            "kind": "finite_union",
            "members": [
                {"kind": "singleton", "value": "MISSING"},
                "Neighbourhood1",
            ],
        },
        "Neighbourhood2": {
            "kind": "finite_product",
            "factors": [
                "LabelOrUnlabelled",
                {"kind": "vectors", "alphabet": "OptionalNeighbourhood1", "length": degree},
            ],
            "formal_source": "LMR Definition 11: N_2(d,Gamma)",
        },
        "TransitionIndex": {
            "kind": "finite_product",
            "factors": ["State", "InputSymbol", "Neighbourhood2"],
        },
    }

    transition_alternative = {
        "index_domain": "TransitionIndex",
        "include_if": "the compile-time delta result has the requested left-hand-side value",
        "body": "Ref(Transition(index))",
    }

    families = (
        RuleFamily(
            "Transition",
            {"index": "TransitionIndex"},
            ({
                "body": "&(symbol State(old_state)) &(symbol Neighbourhood(old_neighbourhood))",
                "expander": "indexed_block_macro_expander.transition_expression",
            },),
            ("State", "Neighbourhood"),
        ),
        RuleFamily(
            "State",
            {"state": "State"},
            (
                {"when": "state == INITIAL", "body": "EOF"},
                transition_alternative,
            ),
            ("Transition",),
        ),
        RuleFamily(
            "Label",
            {"label": "WorkingLabel"},
            (transition_alternative,),
            ("Transition",),
        ),
        RuleFamily(
            "Neighbourhood",
            {"neighbourhood": "Neighbourhood2"},
            (
                {
                    "when": "neighbourhood is the trivial unlabelled base tree",
                    "body": "EOF",
                },
                {
                    "body": (
                        "finite conjunction of root Label, present/missing Path predicates, "
                        "and labels at every present path of length at most two"
                    ),
                    "expander": "indexed_block_macro_expander.neighbourhood_expression",
                },
            ),
            ("Label", "Path", "EOF"),
        ),
        RuleFamily(
            "Path",
            {"path": "PathAtMost2"},
            (
                {"when": "path == epsilon", "body": "epsilon"},
                {
                    "index_domain": "TransitionIndex",
                    "include_if": "the first requested edge is not NONE",
                    "body": (
                        "LMR recurrence: Transition; for PATH consume symbol then Path(target) "
                        "then Path(rest), for SELF continue with Path(rest)"
                    ),
                    "expander": "indexed_block_macro_expander.path_contribution_plan",
                },
            ),
            ("Transition",),
        ),
        RuleFamily(
            "AutomatonAccepts",
            {"singleton": True},
            ({
                "body": (
                    "choice(State(INITIAL) when initial_output=1, "
                    "State((q,1)) for q in BoundaryState) ANY*"
                ),
                "expander": "indexed_block_macro_expander.fixed_full_rules",
            },),
            ("State",),
        ),
    )

    evaluator = {
        "role": "compile-time finite transition-function generator, never a PEG operator",
        "row_enumerator_entrypoint": spec.row_enumerator_entrypoint,
        "ordinary_rows": spec.sparse_row_count,
        "manifest": spec.row_family_manifest,
        "manifest_sha256": spec.row_family_manifest_sha256,
        "algorithm": [
            "enumerate (state, input symbol, exact radius-two neighbourhood)",
            "if state is INITIAL and the neighbourhood is the trivial base, use the blank machine configuration",
            "if state is normal and the neighbourhood decodes as a canonical block snapshot, materialize its three blocks per tape",
            "simulate the deterministic ordinary row stream until the next physical-input boundary",
            f"reject the certificate if more than {spec.delay_bound} primitive transitions occur",
            "compute the next normal state, exact whole working label, and 2*tapes radius-two edge targets",
            "for every other index emit the fixed rejecting SINK transition",
            "fold the resulting total finite delta table into the ordinary LMR rule alternatives",
        ],
        "termination_measure": {
            "finite_transition_index_domain": "State x InputSymbol x Neighbourhood2",
            "primitive_steps_remaining_per_simulation": spec.delay_bound,
            "finite_row_scan_per_step": spec.sparse_row_count,
        },
        "executable_components": {
            "row_stream": spec.row_enumerator_entrypoint,
            "selected_rule_expander": "indexed_block_macro_expander",
            "small_literal_backend": "bounded_delay_macro_compiler.compile_small_bounded_delay_to_peg",
        },
        "optional_acceleration": {
            "kind": "absorbing repeated-square closure",
            "layers": spec.squaring_layers,
            "capacity": spec.macro_capacity,
            "note": "compiler optimization only; no macro operator occurs in the PEG",
        },
    }

    expansion = {
        "entrypoint": "indexed_block_macro_expander",
        "whole_grammar_algorithm": [
            "enumerate every finite State, WorkingLabel, Neighbourhood2, PathAtMost2, and TransitionIndex",
            "compute the total scaffolding transition for every TransitionIndex",
            "add exactly the State, Label, Path, and Transition alternatives in the sufficient direction of LMR Theorem 16",
            "emit each exact Neighbourhood rule as the finite conjunction of Label and Path tests",
            "combine alternatives with prioritized choice; an empty alternative set is FAIL",
        ],
        "standard_operators_only": [
            "epsilon", "terminal", "nonterminal", "sequence", "prioritized choice",
            "and-predicate", "not-predicate", "zero-or-more",
        ],
        "local_audit_backend": "lmr_rule_expander",
        "well_foundedness": (
            "Transition lookahead consumes the newest terminal before State, Label, "
            "Neighbourhood, or Path recursively consults an earlier reversed-input position"
        ),
    }

    proof = {
        "finite_abbreviation": (
            "Every domain above is obtained by finite enum, finite range, finite sum, "
            "finite product, or a fixed-length vector over a finite alphabet.  The nested "
            "generation loops therefore print a finite ordinary PEG."
        ),
        "unique_initial_state": (
            "A synthetic INITIAL state is used only on the unlabelled base and is never "
            "re-entered, matching the normalization used in the LMR proof."
        ),
        "macro_locality": (
            "In at most B unit moves a head starting inside a B-cell aligned block cannot "
            "leave that block and its two neighbours."
        ),
        "one_new_node": (
            "If the final head lies in a neighbouring block, the opposite neighbour was not "
            "visited; the persistent stack update uses paths of length at most two."
        ),
        "total_delta": (
            "Canonical reachable neighbourhoods use exact bounded-delay simulation.  Every "
            "other member of the finite LMR neighbourhood domain is sent to a fixed rejecting "
            "sink state and sink label, so delta is total."
        ),
        "lmr_refinement": (
            "The full families are precisely State(q), Label(gamma), Neighbourhood(N), "
            "Path(p), Transition(q,sigma,N), and AutomatonAccepts from the sufficient direction "
            "of Theorem 16."
        ),
    }

    return SuccinctPEG(
        format="finite indexed ordinary PEG generation plan",
        version=3,
        start_rule="AutomatonAccepts",
        recognizes=spec.language,
        terminal_direction="reverse input (the target language is reversal-invariant)",
        scaffold_degree=degree,
        scaffold_radius=radius,
        block_size=spec.macro_capacity,
        state_predicates=state_predicates,
        path_predicates=path_predicates,
        finite_domains=finite_domains,
        rule_families=families,
        compile_time_transition_oracle=evaluator,
        expansion_algorithm=expansion,
        source_spec={
            "name": spec.name,
            "input_alphabet": list(spec.input_alphabet),
            "tapes": spec.tape_count,
            "states": spec.state_count,
            "boundary_states": list(spec.boundary_states),
            "initial_boundary_state": spec.initial_boundary_state,
            "initial_output": spec.initial_output,
            "blank": spec.blank_symbol,
            "alphabet_descriptors": [asdict(item) for item in spec.alphabet_descriptors],
        },
        proof_obligations=proof,
        status=(
            "explicit finite ordinary-PEG generation algorithm complete; the ordinary text "
            "is astronomical and retained as exact finite indexed comprehensions"
        ),
    )
