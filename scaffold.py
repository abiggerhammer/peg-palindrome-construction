from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Hashable, Iterable, Optional, Sequence, Tuple

Path = Tuple[int, ...]
Label = Optional[Hashable]  # None is reserved for the unlabeled base node.


class TargetKind(str, Enum):
    PATH = "path"
    SELF = "self"
    NONE = "none"


@dataclass(frozen=True)
class Target:
    kind: TargetKind
    path: Path = ()

    @staticmethod
    def via(path: Sequence[int] = ()) -> "Target":
        return Target(TargetKind.PATH, tuple(path))

    @staticmethod
    def self() -> "Target":
        return Target(TargetKind.SELF)

    @staticmethod
    def none() -> "Target":
        return Target(TargetKind.NONE)


class Condition:
    def matches(self, scaffold: "Scaffold", top: int) -> bool:
        raise NotImplementedError


@dataclass(frozen=True)
class Exists(Condition):
    path: Path

    def matches(self, scaffold: "Scaffold", top: int) -> bool:
        return scaffold.follow(top, self.path) is not None


@dataclass(frozen=True)
class Missing(Condition):
    path: Path

    def matches(self, scaffold: "Scaffold", top: int) -> bool:
        return scaffold.follow(top, self.path) is None


@dataclass(frozen=True)
class LabelIs(Condition):
    path: Path
    label: Label

    def matches(self, scaffold: "Scaffold", top: int) -> bool:
        node = scaffold.follow(top, self.path)
        return node is not None and scaffold.labels[node] == self.label




@dataclass(frozen=True)
class FieldIs(Condition):
    path: Path
    field: int
    value: Hashable

    def matches(self, scaffold: "Scaffold", top: int) -> bool:
        node = scaffold.follow(top, self.path)
        if node is None:
            return False
        label = scaffold.labels[node]
        if label is None:
            return False
        try:
            return label[self.field] == self.value  # type: ignore[index]
        except (IndexError, KeyError, TypeError) as exc:
            raise TypeError(
                f"label {label!r} does not expose field {self.field!r}"
            ) from exc


@dataclass(frozen=True)
class Guard:
    conditions: Tuple[Condition, ...] = ()

    @staticmethod
    def all(*conditions: Condition) -> "Guard":
        return Guard(tuple(conditions))

    def matches(self, scaffold: "Scaffold", top: int) -> bool:
        return all(condition.matches(scaffold, top) for condition in self.conditions)


@dataclass(frozen=True)
class Transition:
    state: Hashable
    symbol: str
    guard: Guard
    next_state: Hashable
    new_label: Hashable
    edge_targets: Tuple[Target, ...]
    name: str = ""


@dataclass
class Scaffold:
    degree: int
    labels: list[Label]
    edges: list[Tuple[Optional[int], ...]]

    @classmethod
    def initial(cls, degree: int) -> "Scaffold":
        # Node zero is the unique unlabeled base node.
        return cls(degree=degree, labels=[None], edges=[tuple([None] * degree)])

    @property
    def top(self) -> int:
        return len(self.labels) - 1

    def follow(self, start: int, path: Sequence[int]) -> Optional[int]:
        node: Optional[int] = start
        for edge_index in path:
            if node is None:
                return None
            if not 0 <= edge_index < self.degree:
                raise ValueError(f"edge index {edge_index} outside degree {self.degree}")
            node = self.edges[node][edge_index]
        return node

    def add_node(self, label: Hashable, targets: Sequence[Target]) -> None:
        if len(targets) != self.degree:
            raise ValueError(
                f"transition supplied {len(targets)} edges for degree {self.degree}"
            )
        old_top = self.top
        new_index = old_top + 1
        resolved: list[Optional[int]] = []
        for target in targets:
            if target.kind is TargetKind.NONE:
                resolved.append(None)
            elif target.kind is TargetKind.SELF:
                resolved.append(new_index)
            elif target.kind is TargetKind.PATH:
                resolved.append(self.follow(old_top, target.path))
            else:
                raise ValueError(target.kind)
        self.labels.append(label)
        self.edges.append(tuple(resolved))


@dataclass
class SymbolicScaffoldingAutomaton:
    alphabet: Tuple[str, ...]
    degree: int
    radius: int
    states: Tuple[Hashable, ...]
    initial_state: Hashable
    accepting_states: frozenset[Hashable]
    transitions: Tuple[Transition, ...]

    def __post_init__(self) -> None:
        if len(set(self.alphabet)) != len(self.alphabet):
            raise ValueError("alphabet symbols must be unique")
        if any(len(symbol) != 1 for symbol in self.alphabet):
            raise ValueError("this prototype currently requires one-character terminals")
        for transition in self.transitions:
            if transition.symbol not in self.alphabet:
                raise ValueError(f"transition uses unknown symbol {transition.symbol!r}")
            if len(transition.edge_targets) != self.degree:
                raise ValueError("transition edge count differs from automaton degree")
            for target in transition.edge_targets:
                if target.kind is TargetKind.PATH and len(target.path) > self.radius:
                    raise ValueError(
                        f"target path {target.path} exceeds radius {self.radius}"
                    )
            for condition in transition.guard.conditions:
                path = getattr(condition, "path", ())
                if len(path) > self.radius:
                    raise ValueError(f"guard path {path} exceeds radius {self.radius}")

    def step(
        self, state: Hashable, scaffold: Scaffold, symbol: str
    ) -> tuple[Hashable, Scaffold, Transition]:
        matches = [
            transition
            for transition in self.transitions
            if transition.state == state
            and transition.symbol == symbol
            and transition.guard.matches(scaffold, scaffold.top)
        ]
        if len(matches) != 1:
            names = [transition.name or repr(transition) for transition in matches]
            raise RuntimeError(
                f"expected exactly one transition for state={state!r}, symbol={symbol!r}; "
                f"got {len(matches)}: {names}"
            )
        transition = matches[0]
        scaffold.add_node(transition.new_label, transition.edge_targets)
        return transition.next_state, scaffold, transition

    def run(self, text: str, *, trace: bool = False):
        scaffold = Scaffold.initial(self.degree)
        state = self.initial_state
        history = []
        for symbol in text:
            if symbol not in self.alphabet:
                raise ValueError(f"input contains symbol outside alphabet: {symbol!r}")
            state, scaffold, transition = self.step(state, scaffold, symbol)
            if trace:
                history.append((state, scaffold.top, transition.name))
        accepted = state in self.accepting_states
        if trace:
            return accepted, state, scaffold, history
        return accepted
