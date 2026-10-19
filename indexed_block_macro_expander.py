"""Finite indexed expansion for the bounded-delay block scaffolding compiler.

This module makes the word "indexed" precise.  The full palindrome artifact is
an abbreviation for an ordinary finite PEG: every abbreviation below expands
by a bounded loop over an explicitly finite domain.  The compiler-time macro
oracle is *not* a PEG operator.  For each concrete boundary neighbourhood it
simulates the finite ordinary machine for at most the certified delay and then
emits the ordinary Loff--Moreira--Reis transition alternatives.

The complete expansion is physically absurd, but the functions below can
materialize selected ordinary rules and small instances.  The full backend uses
only the published finite families ``State``, ``Label``, ``Neighbourhood``,
``Path``, ``Transition``, and ``AutomatonAccepts``.  No field predicate or macro
gate is part of the resulting PEG.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Hashable, Mapping, Sequence

from peg import And, Expr, Literal, Not, Ref, seq
from scaffold import Path, Target, TargetKind



def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, tuple):
        return [_jsonable(x) for x in value]
    if isinstance(value, list):
        return [_jsonable(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return {"repr": repr(value)}


def stable_token(value: Any) -> str:
    raw = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True)
class SparseBlock:
    """A concrete vector in ``alphabet**width`` with a default symbol."""

    width: int
    default: Hashable
    exceptions: tuple[tuple[int, Hashable], ...] = ()

    def __post_init__(self) -> None:
        if self.width < 1:
            raise ValueError(self.width)
        seen: set[int] = set()
        for index, value in self.exceptions:
            if not 0 <= index < self.width:
                raise ValueError((index, self.width))
            if index in seen:
                raise ValueError(("duplicate cell", index))
            if value == self.default:
                raise ValueError(("redundant exception", index, value))
            seen.add(index)

    @classmethod
    def from_dense(cls, values: Sequence[Hashable], default: Hashable) -> "SparseBlock":
        return cls(
            len(values),
            default,
            tuple((i, value) for i, value in enumerate(values) if value != default),
        )

    def value_at(self, index: int) -> Hashable:
        for i, value in self.exceptions:
            if i == index:
                return value
        return self.default

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "default": _jsonable(self.default),
            "exceptions": [[i, _jsonable(v)] for i, v in self.exceptions],
        }


@dataclass(frozen=True)
class SideView:
    top: SparseBlock | None
    second: SparseBlock | None

    def __post_init__(self) -> None:
        if self.top is None and self.second is not None:
            raise ValueError("a blank-tail side cannot have a second explicit block")


@dataclass(frozen=True)
class TapeView:
    offset: int
    current: SparseBlock
    left: SideView
    right: SideView

    def __post_init__(self) -> None:
        if not 0 <= self.offset < self.current.width:
            raise ValueError(self.offset)
        for side in (self.left, self.right):
            for block in (side.top, side.second):
                if block is not None and block.width != self.current.width:
                    raise ValueError("inconsistent block width")


@dataclass(frozen=True)
class CanonicalNeighbourhood:
    """The reachable radius-two information used by one block transition."""

    old_output: int
    tapes: tuple[TapeView, ...]

    def __post_init__(self) -> None:
        if self.old_output not in (0, 1):
            raise ValueError(self.old_output)
        if not self.tapes:
            raise ValueError("empty tape product")
        width = self.tapes[0].current.width
        if any(tape.current.width != width for tape in self.tapes):
            raise ValueError("mixed block widths")

    @property
    def block_size(self) -> int:
        return self.tapes[0].current.width


@dataclass(frozen=True)
class FullNeighbourhood:
    """One exact LMR radius-bounded neighbourhood tree.

    ``label=None`` is the unlabelled base marker.  A ``None`` child is a
    missing edge; a non-``None`` child is another exact subtree.  The degree
    and remaining radius are fixed by the surrounding finite index domain.
    """

    label: Any | None
    children: tuple["FullNeighbourhood | None", ...] = ()

    def __post_init__(self) -> None:
        # The formal LMR N_k domain includes trees that are unreachable in an
        # actual scaffold, such as an unlabelled root with present children.
        # They are retained here so the compiler can give delta a total sink
        # completion.
        if any(child is not None and not isinstance(child, FullNeighbourhood) for child in self.children):
            raise TypeError(self.children)

    @property
    def degree(self) -> int:
        return len(self.children)


INITIAL_STATE = ("INITIAL",)
SINK_STATE = ("SINK",)
SINK_LABEL = {"kind": "sink"}


def normal_state(boundary: int, output: int) -> tuple[str, int, int]:
    if output not in (0, 1):
        raise ValueError(output)
    return ("NORMAL", boundary, output)


@dataclass(frozen=True)
class TransitionIndex:
    old_state: Hashable
    input_symbol: str
    neighbourhood: FullNeighbourhood

    def id(self) -> str:
        payload = {
            "state": _jsonable(self.old_state),
            "a": self.input_symbol,
            "n": full_neighbourhood_dict(self.neighbourhood),
        }
        return stable_token(payload)


@dataclass(frozen=True)
class TransitionOutcome:
    next_state: Hashable
    output: int
    new_tapes: tuple[TapeView, ...]
    edge_targets: tuple[Target, ...]
    primitive_steps: int

    def __post_init__(self) -> None:
        if self.output not in (0, 1):
            raise ValueError(self.output)
        if self.primitive_steps < 1:
            raise ValueError(self.primitive_steps)
        if len(self.edge_targets) != 2 * len(self.new_tapes):
            raise ValueError("wrong edge arity")


def block_dict(block: SparseBlock | None) -> Any:
    return None if block is None else block.to_dict()


def canonical_label_dict(output: int, tapes: Sequence[TapeView]) -> dict[str, Any]:
    """The exact finite working-alphabet symbol stored at one scaffold node."""

    if output not in (0, 1):
        raise ValueError(output)
    return {
        "kind": "canonical",
        "output": output,
        "tapes": [
            {
                "offset": tape.offset,
                "current": tape.current.to_dict(),
                "left_top": block_dict(tape.left.top),
                "right_top": block_dict(tape.right.top),
            }
            for tape in tapes
        ],
    }


def full_neighbourhood_dict(value: FullNeighbourhood) -> dict[str, Any]:
    return {
        "label": _jsonable(value.label),
        "children": [
            None if child is None else full_neighbourhood_dict(child)
            for child in value.children
        ],
    }


def base_neighbourhood(degree: int) -> FullNeighbourhood:
    if degree < 1:
        raise ValueError(degree)
    return FullNeighbourhood(None, tuple(None for _ in range(degree)))


def label_name(label: Any) -> str:
    if label == SINK_LABEL:
        return "Label_SINK"
    return "Label_" + stable_token(label)


def neighbourhood_name(neighbourhood: FullNeighbourhood) -> str:
    return "Neighbourhood_" + stable_token(full_neighbourhood_dict(neighbourhood))


def state_name(state: Hashable) -> str:
    if state == INITIAL_STATE:
        return "State_INITIAL"
    if state == SINK_STATE:
        return "State_SINK"
    if isinstance(state, tuple) and len(state) == 3 and state[0] == "NORMAL":
        return f"State_q{state[1]}_o{state[2]}"
    return "State_h" + stable_token(state)


def path_name(path: Path) -> str:
    return "Path_eps" if not path else "Path_" + "_".join(map(str, path))


def transition_name(index: TransitionIndex) -> str:
    return f"Transition_{index.id()}"


def _label_at_path(path: Path, label: Any | None) -> Expr:
    predicate: Expr = Ref("EOF") if label is None else Ref(label_name(label))
    if not path:
        return predicate
    return And(seq(Ref(path_name(path)), predicate))


def neighbourhood_expression(neighbourhood: FullNeighbourhood) -> Expr:
    """Materialize the published exact ``Neighbourhood(N)`` predicate."""

    parts: list[Expr] = [_label_at_path((), neighbourhood.label)]

    def walk(node: FullNeighbourhood, prefix: Path) -> None:
        for edge, child in enumerate(node.children):
            path = prefix + (edge,)
            if child is None:
                parts.append(Not(Ref(path_name(path))))
                continue
            parts.append(And(Ref(path_name(path))))
            parts.append(_label_at_path(path, child.label))
            walk(child, path)

    walk(neighbourhood, ())
    return seq(*parts)


def neighbourhood_plan(neighbourhood: FullNeighbourhood) -> dict[str, Any]:
    return {
        "lhs": neighbourhood_name(neighbourhood),
        "body": {
            "op": "exact_lmr_neighbourhood",
            "tree": full_neighbourhood_dict(neighbourhood),
            "semantics": (
                "finite conjunction of root/path labels, present paths, and missing paths"
            ),
        },
        "ordinary_expander": "indexed_block_macro_expander.neighbourhood_expression",
    }


def transition_expression(index: TransitionIndex) -> Expr:
    symbol = Literal(index.input_symbol)
    return seq(
        And(seq(symbol, Ref(state_name(index.old_state)))),
        And(seq(symbol, Ref(neighbourhood_name(index.neighbourhood)))),
    )


def transition_plan(index: TransitionIndex) -> dict[str, Any]:
    return {
        "lhs": transition_name(index),
        "body": {
            "op": "seq",
            "items": [
                {
                    "op": "and",
                    "body": {
                        "op": "seq",
                        "items": [
                            {"op": "literal", "text": index.input_symbol},
                            {"op": "ref", "name": state_name(index.old_state)},
                        ],
                    },
                },
                {
                    "op": "and",
                    "body": {
                        "op": "seq",
                        "items": [
                            {"op": "literal", "text": index.input_symbol},
                            {"op": "ref", "name": neighbourhood_name(index.neighbourhood)},
                        ],
                    },
                },
            ],
        },
        "ordinary_expander": "indexed_block_macro_expander.transition_expression",
    }


def label_contribution_plan(index: TransitionIndex, outcome: TransitionOutcome) -> dict[str, Any]:
    label = canonical_label_dict(outcome.output, outcome.new_tapes)
    return {
        "lhs": label_name(label),
        "body": {"op": "ref", "name": transition_name(index)},
        "label": label,
    }


def state_contribution_plan(index: TransitionIndex, outcome: TransitionOutcome) -> dict[str, Any]:
    return {
        "lhs": state_name(outcome.next_state),
        "body": {"op": "ref", "name": transition_name(index)},
    }


def path_contribution_plan(
    index: TransitionIndex, outcome: TransitionOutcome, path: Path
) -> dict[str, Any] | None:
    if not path:
        raise ValueError("epsilon path has the fixed epsilon rule")
    edge, rest = path[0], path[1:]
    target = outcome.edge_targets[edge]
    if target.kind is TargetKind.NONE:
        return None
    parts: list[dict[str, Any]] = [
        {"op": "ref", "name": transition_name(index)},
    ]
    if target.kind is TargetKind.SELF:
        parts.append({"op": "ref", "name": path_name(rest)})
    elif target.kind is TargetKind.PATH:
        parts.extend((
            {"op": "literal", "text": index.input_symbol},
            {"op": "ref", "name": path_name(target.path)},
            {"op": "ref", "name": path_name(rest)},
        ))
    else:  # pragma: no cover
        raise ValueError(target.kind)
    return {"lhs": path_name(path), "body": {"op": "seq", "items": parts}}


def fixed_full_rules(
    *, degree: int, initial_output: int, boundary_states: Sequence[int]
) -> dict[str, dict[str, Any]]:
    accepting = [
        {"op": "ref", "name": state_name(normal_state(q, 1))}
        for q in boundary_states
    ]
    if initial_output == 1:
        accepting.insert(0, {"op": "ref", "name": state_name(INITIAL_STATE)})
    base = base_neighbourhood(degree)
    return {
        "EOF": {"op": "not", "body": {"op": "any"}},
        path_name(()): {"op": "epsilon"},
        "InitialStateEOFAlternative": {
            "lhs": state_name(INITIAL_STATE),
            "body": {"op": "ref", "name": "EOF"},
        },
        "InitialNeighbourhoodEOFAlternative": {
            "lhs": neighbourhood_name(base),
            "body": {"op": "ref", "name": "EOF"},
        },
        "AutomatonAccepts": {
            "op": "seq",
            "items": [
                {"op": "choice", "items": accepting},
                {"op": "star", "body": {"op": "any"}},
            ],
        },
    }

def render_plan(node: Mapping[str, Any]) -> str:
    """Readable mathematical rendering of a selected indexed expression."""

    op = node.get("op")
    if op == "epsilon":
        return "ε"
    if op == "any":
        return "."
    if op == "literal":
        return repr(node["text"])
    if op == "ref":
        return str(node["name"])
    if op == "seq":
        return " ".join(render_plan(x) for x in node["items"])
    if op == "choice":
        return " / ".join(render_plan(x) for x in node["items"])
    if op == "and":
        return "&(" + render_plan(node["body"]) + ")"
    if op == "not":
        return "!(" + render_plan(node["body"]) + ")"
    if op == "star":
        return "(" + render_plan(node["body"]) + ")*"
    if op == "exact_lmr_neighbourhood":
        return "ExactLMRNeighbourhood[" + stable_token(node["tree"]) + "]"
    raise ValueError(node)


def state_contribution_from_values(
    index: TransitionIndex, *, next_boundary_state: int, output: int
) -> dict[str, Any]:
    return {
        "lhs": state_name(normal_state(next_boundary_state, output)),
        "body": {"op": "ref", "name": transition_name(index)},
    }


# ---------------------------------------------------------------------------
# Executable compile-time transition oracle.


def _atom_matches(atom: Any, actual: Hashable) -> bool:
    if atom is None:
        return True
    if isinstance(atom, frozenset):
        return actual in atom
    return atom == actual


def streaming_row_for(
    row_factory,
    *,
    state: int,
    input_symbol: str,
    scanned: Sequence[Hashable],
):
    """Find the unique matching sparse row by a finite stream scan.

    This is intentionally austere.  Production implementations may index the
    row families, but a complete scan of the certified finite stream is already
    an effective transition oracle and is easier to audit.
    """

    found = None
    for row in row_factory():
        if row.state != state:
            continue
        if row.input_symbol is not None and row.input_symbol != input_symbol:
            continue
        if all(_atom_matches(atom, scanned[tape]) for tape, atom in row.reads):
            if found is not None and found.action != row.action:
                raise AssertionError(("nondeterministic scheduled rows", found, row))
            found = row
    if found is None:
        raise LookupError(("no scheduled row", state, input_symbol, tuple(scanned)))
    return found


def _dense(block: SparseBlock | None, *, width: int, blank: Hashable) -> tuple[Hashable, ...]:
    if block is None:
        return tuple(blank for _ in range(width))
    return tuple(block.value_at(i) for i in range(width))


def _sparse(values: Sequence[Hashable], *, blank: Hashable) -> SparseBlock:
    return SparseBlock.from_dense(tuple(values), blank)


def _is_blank(block: Sequence[Hashable], blank: Hashable) -> bool:
    return all(value == blank for value in block)


def _canonical_side_after_stay(
    block: Sequence[Hashable], old: SideView, *, blank: Hashable
) -> SideView:
    if old.top is None and _is_blank(block, blank):
        return SideView(None, None)
    return SideView(_sparse(block, blank=blank), old.second)


def _edge_targets_for_regions(
    old: CanonicalNeighbourhood,
    new_tapes: Sequence[TapeView],
    regions: Sequence[int],
) -> tuple[Target, ...]:
    targets: list[Target] = []
    for tape, (before, after, region) in enumerate(zip(old.tapes, new_tapes, regions)):
        left_edge = 2 * tape
        right_edge = left_edge + 1
        if region == 0:
            left = Target.none() if after.left.top is None else Target.via((left_edge,))
            right = Target.none() if after.right.top is None else Target.via((right_edge,))
        elif region == 1:
            left = Target.none() if before.left.top is None else Target.via(())
            right = (
                Target.none()
                if after.right.top is None
                else Target.via((right_edge, right_edge))
            )
        elif region == -1:
            left = (
                Target.none()
                if after.left.top is None
                else Target.via((left_edge, left_edge))
            )
            right = Target.none() if before.right.top is None else Target.via(())
        else:
            raise ValueError(region)
        targets.extend((left, right))
    return tuple(targets)


def simulate_streaming_interval(
    *,
    row_factory,
    tape_count: int,
    blank: Hashable,
    boundary_state: int,
    input_symbol: str,
    neighbourhood: CanonicalNeighbourhood,
    delay_bound: int,
) -> TransitionOutcome:
    """Execute one bounded-delay interval from an exact canonical snapshot."""

    if len(neighbourhood.tapes) != tape_count:
        raise ValueError((len(neighbourhood.tapes), tape_count))
    width = neighbourhood.block_size
    if width < delay_bound:
        raise ValueError((width, delay_bound))

    stores: list[dict[int, Hashable]] = []
    heads: list[int] = []
    original_left: list[tuple[Hashable, ...]] = []
    original_right: list[tuple[Hashable, ...]] = []
    for tape in neighbourhood.tapes:
        left = _dense(tape.left.top, width=width, blank=blank)
        current = _dense(tape.current, width=width, blank=blank)
        right = _dense(tape.right.top, width=width, blank=blank)
        store: dict[int, Hashable] = {}
        for base, block in ((-width, left), (0, current), (width, right)):
            for i, value in enumerate(block):
                if value != blank:
                    store[base + i] = value
        stores.append(store)
        heads.append(tape.offset)
        original_left.append(left)
        original_right.append(right)

    state = boundary_state
    emitted = None
    steps = 0
    while True:
        scanned = tuple(
            stores[tape].get(heads[tape], blank) for tape in range(tape_count)
        )
        row = streaming_row_for(
            row_factory,
            state=state,
            input_symbol=input_symbol,
            scanned=scanned,
        )
        writes = dict(row.action.writes)
        moves = dict(row.action.moves)
        for tape, old_value in enumerate(scanned):
            value = writes.get(tape, old_value)
            if value == blank:
                stores[tape].pop(heads[tape], None)
            else:
                stores[tape][heads[tape]] = value
            heads[tape] += moves.get(tape, 0)
            if not -width <= heads[tape] < 2 * width:
                raise AssertionError(("head escaped three-block window", tape, heads[tape], steps))
        if row.action.emit is not None:
            if emitted is not None:
                raise AssertionError("multiple outputs in one physical interval")
            emitted = row.action.emit
        state = row.action.next_state
        steps += 1
        if row.action.input_move:
            if row.action.input_move != 1:
                raise AssertionError(("unexpected physical input move", row.action.input_move))
            break
        if steps >= delay_bound:
            raise TimeoutError((state, steps, delay_bound))

    if emitted not in (0, 1):
        raise AssertionError(("missing physical output", emitted))

    new_tapes: list[TapeView] = []
    regions: list[int] = []
    for tape_index, old in enumerate(neighbourhood.tapes):
        def block_at(base: int) -> tuple[Hashable, ...]:
            return tuple(
                stores[tape_index].get(base + i, blank) for i in range(width)
            )

        left = block_at(-width)
        current = block_at(0)
        right = block_at(width)
        head = heads[tape_index]
        if head < 0:
            if right != original_right[tape_index]:
                raise AssertionError("left-ending interval modified right neighbour")
            regions.append(-1)
            new_tapes.append(TapeView(
                offset=head + width,
                current=_sparse(left, blank=blank),
                left=SideView(old.left.second, None),
                right=SideView(_sparse(current, blank=blank), old.right.top),
            ))
        elif head >= width:
            if left != original_left[tape_index]:
                raise AssertionError("right-ending interval modified left neighbour")
            regions.append(1)
            new_tapes.append(TapeView(
                offset=head - width,
                current=_sparse(right, blank=blank),
                left=SideView(_sparse(current, blank=blank), old.left.top),
                right=SideView(old.right.second, None),
            ))
        else:
            regions.append(0)
            new_tapes.append(TapeView(
                offset=head,
                current=_sparse(current, blank=blank),
                left=_canonical_side_after_stay(left, old.left, blank=blank),
                right=_canonical_side_after_stay(right, old.right, blank=blank),
            ))

    return TransitionOutcome(
        next_state=normal_state(state, emitted),
        output=emitted,
        new_tapes=tuple(new_tapes),
        edge_targets=_edge_targets_for_regions(neighbourhood, new_tapes, regions),
        primitive_steps=steps,
    )


def _block_from_dict(value: Any, *, width: int, blank: Hashable) -> SparseBlock | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(value)
    block = SparseBlock(
        int(value["width"]),
        value["default"],
        tuple((int(i), symbol) for i, symbol in value.get("exceptions", ())),
    )
    if block.width != width or block.default != blank:
        raise ValueError((block.width, block.default, width, blank))
    return block


def decode_canonical_neighbourhood(
    neighbourhood: FullNeighbourhood,
    *,
    tape_count: int,
    block_size: int,
    blank: Hashable,
) -> CanonicalNeighbourhood | None:
    """Decode the reachable block projection of an exact LMR neighbourhood."""

    label = neighbourhood.label
    if not isinstance(label, Mapping) or label.get("kind") != "canonical":
        return None
    tape_labels = label.get("tapes")
    if not isinstance(tape_labels, list) or len(tape_labels) != tape_count:
        return None
    if len(neighbourhood.children) != 2 * tape_count:
        return None

    tapes: list[TapeView] = []
    for tape_index, item in enumerate(tape_labels):
        if not isinstance(item, Mapping):
            return None
        current = _block_from_dict(item.get("current"), width=block_size, blank=blank)
        left_top = _block_from_dict(item.get("left_top"), width=block_size, blank=blank)
        right_top = _block_from_dict(item.get("right_top"), width=block_size, blank=blank)
        if current is None:
            return None

        sides: list[SideView] = []
        for side_name, top, edge in (
            ("left_top", left_top, 2 * tape_index),
            ("right_top", right_top, 2 * tape_index + 1),
        ):
            child = neighbourhood.children[edge]
            if top is None:
                if child is not None:
                    return None
                sides.append(SideView(None, None))
                continue
            if child is None or not isinstance(child.label, Mapping):
                return None
            child_tapes = child.label.get("tapes")
            if child.label.get("kind") != "canonical" or not isinstance(child_tapes, list):
                return None
            second = _block_from_dict(
                child_tapes[tape_index].get(side_name),
                width=block_size,
                blank=blank,
            )
            sides.append(SideView(top, second))
        tapes.append(TapeView(
            offset=int(item["offset"]),
            current=current,
            left=sides[0],
            right=sides[1],
        ))

    return CanonicalNeighbourhood(int(label["output"]), tuple(tapes))


def total_delta_plan(
    index: TransitionIndex,
    *,
    row_factory,
    tape_count: int,
    blank: Hashable,
    initial_boundary_state: int,
    initial_output: int,
    block_size: int,
    delay_bound: int,
) -> dict[str, Any]:
    """Compute one member of the total finite scaffolding transition table."""

    if index.old_state == SINK_STATE:
        return {
            "next_state": SINK_STATE,
            "label": SINK_LABEL,
            "edge_targets": ["NONE"] * (2 * tape_count),
            "primitive_steps": 1,
            "kind": "sink",
        }

    canonical = None
    boundary = None
    if index.old_state == INITIAL_STATE:
        if index.neighbourhood == base_neighbourhood(2 * tape_count):
            blank_block = SparseBlock(block_size, blank)
            canonical = CanonicalNeighbourhood(
                initial_output,
                tuple(
                    TapeView(0, blank_block, SideView(None, None), SideView(None, None))
                    for _ in range(tape_count)
                ),
            )
            boundary = initial_boundary_state
    elif (
        isinstance(index.old_state, tuple)
        and len(index.old_state) == 3
        and index.old_state[0] == "NORMAL"
    ):
        boundary = int(index.old_state[1])
        old_output = int(index.old_state[2])
        canonical = decode_canonical_neighbourhood(
            index.neighbourhood,
            tape_count=tape_count,
            block_size=block_size,
            blank=blank,
        )
        if canonical is not None and canonical.old_output != old_output:
            canonical = None

    if canonical is None or boundary is None:
        return {
            "next_state": SINK_STATE,
            "label": SINK_LABEL,
            "edge_targets": ["NONE"] * (2 * tape_count),
            "primitive_steps": 1,
            "kind": "sink_completion",
        }

    outcome = simulate_streaming_interval(
        row_factory=row_factory,
        tape_count=tape_count,
        blank=blank,
        boundary_state=boundary,
        input_symbol=index.input_symbol,
        neighbourhood=canonical,
        delay_bound=delay_bound,
    )
    return {
        "next_state": outcome.next_state,
        "label": canonical_label_dict(outcome.output, outcome.new_tapes),
        "edge_targets": [
            {"kind": target.kind.value, "path": list(target.path)}
            for target in outcome.edge_targets
        ],
        "primitive_steps": outcome.primitive_steps,
        "kind": "canonical",
    }
