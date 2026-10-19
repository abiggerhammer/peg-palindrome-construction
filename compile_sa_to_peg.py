from __future__ import annotations

from collections import defaultdict

from peg import Grammar, choice
from scaffold import SymbolicScaffoldingAutomaton
from lmr_rule_expander import (
    LMRNames,
    all_paths,
    field_contributions,
    fixed_rules,
    guard_expression,
    guard_name,
    label_contribution,
    path_contribution,
    path_name,
    state_contribution,
    transition_expression,
    transition_name,
)


def compile_to_peg(automaton: SymbolicScaffoldingAutomaton) -> Grammar:
    """Compile a symbolic scaffolding automaton to a PEG for the reverse language.

    This is the sufficient direction of Theorem 16 in Loff--Moreira--Reis.
    ``FieldIs`` is a finite product-alphabet abbreviation of whole-label tests;
    :mod:`lmr_rule_expander` exposes each ordinary rule contribution separately.
    """

    names = LMRNames.from_automaton(automaton)
    rules = dict(fixed_rules(automaton, names))
    alternatives: dict[str, list] = defaultdict(list)

    # The initial-state EOF alternative may share a rule with ordinary
    # transition alternatives.  Move fixed contributions into the same fold.
    for lhs in tuple(rules):
        if lhs.startswith("State_"):
            alternatives[lhs].append(rules.pop(lhs))

    for index, _transition in enumerate(automaton.transitions):
        rules[guard_name(index)] = guard_expression(_transition, names)
        rules[transition_name(index)] = transition_expression(automaton, index, names)

        lhs, body = state_contribution(automaton, index, names)
        alternatives[lhs].append(body)
        label = label_contribution(automaton, index, names)
        if label is not None:
            alternatives[label[0]].append(label[1])
        for lhs, body in field_contributions(automaton, index, names):
            alternatives[lhs].append(body)
        for path in all_paths(automaton.degree, automaton.radius):
            if not path:
                continue
            item = path_contribution(automaton, path, index)
            if item is not None:
                alternatives[item[0]].append(item[1])

    for state in automaton.states:
        lhs = names.state(state)
        rules[lhs] = choice(*alternatives[lhs])
    for label in names.label_ids:
        lhs = names.label(label)
        rules[lhs] = choice(*alternatives[lhs])
    for field, value in names.field_ids:
        lhs = names.field(field, value)
        rules[lhs] = choice(*alternatives[lhs])
    for path in all_paths(automaton.degree, automaton.radius):
        if path:
            lhs = path_name(path)
            rules[lhs] = choice(*alternatives[lhs])

    return Grammar(rules=rules, start="AutomatonAccepts")
