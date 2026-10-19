"""On-demand expansion of the Loff--Moreira--Reis SA-to-PEG rules.

The sufficient direction of Theorem 16 is local: each scaffolding transition
contributes one alternative to a state rule, zero or one alternatives to label
and field rules, and zero or one alternative to each path rule.  This module
exposes those contributions directly.  :mod:`compile_sa_to_peg` is the finite
whole-grammar fold over the same functions.

``FieldIs`` is a conservative product-alphabet refinement of the published
``Label`` predicate.  A label is a finite tuple.  Testing one coordinate is
exactly the finite disjunction of all whole labels having that coordinate, so
it does not add power or alter the ordinary PEG expansion.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Hashable

from peg import ANY, EPS, And, Expr, Literal, Not, Ref, Star, choice, seq
from scaffold import (
    Exists,
    FieldIs,
    LabelIs,
    Missing,
    Path,
    SymbolicScaffoldingAutomaton,
    TargetKind,
    Transition,
)


def all_paths(degree: int, radius: int) -> tuple[Path, ...]:
    paths: list[Path] = [()]
    for length in range(1, radius + 1):
        paths.extend(tuple(p) for p in product(range(degree), repeat=length))
    return tuple(paths)


def path_name(path: Path) -> str:
    return "Path_eps" if not path else "Path_" + "_".join(map(str, path))


@dataclass(frozen=True)
class LMRNames:
    state_ids: dict[Hashable, int]
    label_ids: dict[Hashable, int]
    field_ids: dict[tuple[Hashable, Hashable], int]

    @classmethod
    def from_automaton(cls, automaton: SymbolicScaffoldingAutomaton) -> "LMRNames":
        state_ids = {state: index for index, state in enumerate(automaton.states)}

        labels: list[Hashable] = []
        seen_labels: set[Hashable] = set()
        fields: list[tuple[Hashable, Hashable]] = []
        seen_fields: set[tuple[Hashable, Hashable]] = set()
        for transition in automaton.transitions:
            for condition in transition.guard.conditions:
                if isinstance(condition, LabelIs) and condition.label is not None:
                    if condition.label not in seen_labels:
                        seen_labels.add(condition.label)
                        labels.append(condition.label)
                elif isinstance(condition, FieldIs):
                    key = (condition.field, condition.value)
                    if key not in seen_fields:
                        seen_fields.add(key)
                        fields.append(key)
        return cls(
            state_ids,
            {label: index for index, label in enumerate(labels)},
            {field: index for index, field in enumerate(fields)},
        )

    def state(self, q: Hashable) -> str:
        return f"State_{self.state_ids[q]}"

    def label(self, gamma: Hashable) -> str:
        return f"Label_{self.label_ids[gamma]}"

    def field(self, field: Hashable, value: Hashable) -> str:
        return f"Field_{self.field_ids[(field, value)]}"


def guard_expression(transition: Transition, names: LMRNames) -> Expr:
    """Expand one symbolic guard into ordinary PEG lookahead predicates."""

    parts: list[Expr] = []
    for condition in transition.guard.conditions:
        p = Ref(path_name(condition.path))
        if isinstance(condition, Exists):
            parts.append(And(p))
        elif isinstance(condition, Missing):
            parts.append(Not(p))
        elif isinstance(condition, LabelIs):
            if condition.label is None:
                parts.append(And(seq(p, Ref("EOF"))))
            else:
                parts.append(And(seq(p, Ref(names.label(condition.label)))))
        elif isinstance(condition, FieldIs):
            parts.append(And(seq(p, Ref(names.field(condition.field, condition.value)))))
        else:  # pragma: no cover - closed condition hierarchy
            raise TypeError(condition)
    return seq(*parts)


def transition_expression(
    automaton: SymbolicScaffoldingAutomaton,
    transition_index: int,
    names: LMRNames | None = None,
) -> Expr:
    """The published ``Transition(q, sigma, N)`` predicate for one row."""

    names = names or LMRNames.from_automaton(automaton)
    transition = automaton.transitions[transition_index]
    symbol = Literal(transition.symbol)
    return seq(
        And(seq(symbol, Ref(names.state(transition.state)))),
        And(seq(symbol, guard_expression(transition, names))),
    )


def transition_name(index: int) -> str:
    return f"Transition_{index}"


def guard_name(index: int) -> str:
    return f"Guard_{index}"


def state_contribution(
    automaton: SymbolicScaffoldingAutomaton,
    transition_index: int,
    names: LMRNames | None = None,
) -> tuple[str, Expr]:
    names = names or LMRNames.from_automaton(automaton)
    transition = automaton.transitions[transition_index]
    return names.state(transition.next_state), Ref(transition_name(transition_index))


def label_contribution(
    automaton: SymbolicScaffoldingAutomaton,
    transition_index: int,
    names: LMRNames | None = None,
) -> tuple[str, Expr] | None:
    names = names or LMRNames.from_automaton(automaton)
    transition = automaton.transitions[transition_index]
    if transition.new_label not in names.label_ids:
        return None
    return names.label(transition.new_label), Ref(transition_name(transition_index))


def field_contributions(
    automaton: SymbolicScaffoldingAutomaton,
    transition_index: int,
    names: LMRNames | None = None,
) -> tuple[tuple[str, Expr], ...]:
    names = names or LMRNames.from_automaton(automaton)
    transition = automaton.transitions[transition_index]
    out: list[tuple[str, Expr]] = []
    for field, value in names.field_ids:
        try:
            actual = transition.new_label[field]
        except (IndexError, KeyError, TypeError) as exc:
            raise TypeError(
                f"label {transition.new_label!r} does not expose field {field!r}"
            ) from exc
        if actual == value:
            out.append((names.field(field, value), Ref(transition_name(transition_index))))
    return tuple(out)


def path_contribution(
    automaton: SymbolicScaffoldingAutomaton,
    path: Path,
    transition_index: int,
) -> tuple[str, Expr] | None:
    """One transition's alternative for ``Path(path)``.

    This is equations (the three cases for an ordinary path, ``SELF``, and
    missing edge) in the sufficient-direction proof of Theorem 16.
    """

    if not path:
        raise ValueError("Path(epsilon) has the fixed epsilon rule")
    transition = automaton.transitions[transition_index]
    edge, rest = path[0], path[1:]
    target = transition.edge_targets[edge]
    t = Ref(transition_name(transition_index))
    if target.kind is TargetKind.NONE:
        return None
    if target.kind is TargetKind.SELF:
        body = seq(t, Ref(path_name(rest)))
    elif target.kind is TargetKind.PATH:
        body = seq(
            t,
            Literal(transition.symbol),
            Ref(path_name(target.path)),
            Ref(path_name(rest)),
        )
    else:  # pragma: no cover
        raise ValueError(target.kind)
    return path_name(path), body


def fixed_rules(automaton: SymbolicScaffoldingAutomaton, names: LMRNames | None = None):
    """Rules not obtained by folding transition contributions."""

    names = names or LMRNames.from_automaton(automaton)
    alphabet = choice(*(Literal(symbol) for symbol in automaton.alphabet))
    accepting = choice(*(Ref(names.state(q)) for q in automaton.accepting_states))
    return {
        "EOF": Not(ANY),
        names.state(automaton.initial_state): Ref("EOF"),
        path_name(()): EPS,
        "AutomatonAccepts": seq(accepting, Star(ANY)),
    }
