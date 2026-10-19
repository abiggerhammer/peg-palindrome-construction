import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compile_palindrome_succinct_peg import build_spec, main
from constant_speedup import MACRO_CAPACITY
from scheduled_source_composition import BOUNDED_DELAY_TRANSITIONS, SCHEDULED_WORK_TAPES
from build_outer_service_fabric import build_fabric
from succinct_block_peg import compile_bounded_delay_to_succinct_peg


def test_full_palindrome_schema_is_finite_and_radius_two(tmp_path: Path):
    spec = build_spec()
    grammar = compile_bounded_delay_to_succinct_peg(spec)
    assert grammar.block_size == MACRO_CAPACITY == 2**39
    assert grammar.block_size >= BOUNDED_DELAY_TRANSITIONS
    assert grammar.scaffold_degree == 2 * SCHEDULED_WORK_TAPES == 590
    assert grammar.scaffold_radius == 2
    assert grammar.path_predicates == 1 + 590 + 590 * 590
    assert grammar.version == 3
    assert grammar.compile_time_transition_oracle["optional_acceleration"]["layers"] == 39
    assert grammar.compile_time_transition_oracle["role"].startswith("compile-time")
    names = {family.name for family in grammar.rule_families}
    assert names == {"Transition", "State", "Label", "Neighbourhood", "Path", "AutomatonAccepts"}
    assert grammar.finite_domains["TransitionIndex"]["kind"] == "finite_product"
    assert grammar.finite_domains["State"]["cardinality"] == 6
    assert grammar.state_predicates == 6
    assert grammar.proof_obligations["total_delta"].startswith("Canonical reachable")
    continuation_tape = build_fabric().continuation_tape
    alphabets = grammar.finite_domains["TapeAlphabet"]
    assert alphabets[continuation_tape]["cardinality"] == 2445

    output = tmp_path / "palindrome.speg.json"
    certificate = tmp_path / "certificate.json"
    first = main(output, certificate)
    first_bytes = output.read_bytes()
    second = main(output, certificate)
    assert output.read_bytes() == first_bytes
    data = json.loads(output.read_text())
    assert data["start_rule"] == "AutomatonAccepts"
    assert data["source_spec"]["initial_output"] == 1
    assert first["certificate"]["grammar_sha256"] == second["certificate"]["grammar_sha256"]
