from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence, Tuple


class Expr:
    """Base class for a small, standard PEG expression AST."""


@dataclass(frozen=True)
class Epsilon(Expr):
    pass


@dataclass(frozen=True)
class Fail(Expr):
    pass


@dataclass(frozen=True)
class Literal(Expr):
    text: str


@dataclass(frozen=True)
class AnyChar(Expr):
    pass


@dataclass(frozen=True)
class Ref(Expr):
    name: str


@dataclass(frozen=True)
class SeqExpr(Expr):
    parts: Tuple[Expr, ...]


@dataclass(frozen=True)
class Choice(Expr):
    alternatives: Tuple[Expr, ...]


@dataclass(frozen=True)
class And(Expr):
    body: Expr


@dataclass(frozen=True)
class Not(Expr):
    body: Expr


@dataclass(frozen=True)
class Star(Expr):
    body: Expr


EPS = Epsilon()
FAIL = Fail()
ANY = AnyChar()


def seq(*parts: Expr) -> Expr:
    flat: list[Expr] = []
    for part in parts:
        if isinstance(part, Epsilon):
            continue
        if isinstance(part, SeqExpr):
            flat.extend(part.parts)
        else:
            flat.append(part)
    if not flat:
        return EPS
    if len(flat) == 1:
        return flat[0]
    return SeqExpr(tuple(flat))


def choice(*alternatives: Expr) -> Expr:
    flat: list[Expr] = []
    for alt in alternatives:
        if isinstance(alt, Choice):
            flat.extend(alt.alternatives)
        else:
            flat.append(alt)
    if not flat:
        return FAIL
    if len(flat) == 1:
        return flat[0]
    return Choice(tuple(flat))


@dataclass
class Grammar:
    rules: Dict[str, Expr]
    start: str

    def recognize(self, text: str) -> bool:
        """Recognize text using packrat-style memoization.

        The result is standard PEG recognition: the start expression must consume
        the entire input. Generated grammars in this project also make that
        explicit in their start rule.
        """

        memo: dict[tuple[str, int], Optional[int]] = {}
        active: set[tuple[str, int]] = set()

        def run(expr: Expr, pos: int) -> Optional[int]:
            if isinstance(expr, Epsilon):
                return pos
            if isinstance(expr, Fail):
                return None
            if isinstance(expr, Literal):
                if text.startswith(expr.text, pos):
                    return pos + len(expr.text)
                return None
            if isinstance(expr, AnyChar):
                return pos + 1 if pos < len(text) else None
            if isinstance(expr, Ref):
                key = (expr.name, pos)
                if key in memo:
                    return memo[key]
                if key in active:
                    raise RuntimeError(
                        f"left recursion or zero-progress recursion at {expr.name}@{pos}"
                    )
                try:
                    body = self.rules[expr.name]
                except KeyError as exc:
                    raise KeyError(f"undefined PEG nonterminal: {expr.name}") from exc
                active.add(key)
                try:
                    result = run(body, pos)
                finally:
                    active.remove(key)
                memo[key] = result
                return result
            if isinstance(expr, SeqExpr):
                cur = pos
                for part in expr.parts:
                    nxt = run(part, cur)
                    if nxt is None:
                        return None
                    cur = nxt
                return cur
            if isinstance(expr, Choice):
                for alt in expr.alternatives:
                    result = run(alt, pos)
                    if result is not None:
                        return result
                return None
            if isinstance(expr, And):
                return pos if run(expr.body, pos) is not None else None
            if isinstance(expr, Not):
                return pos if run(expr.body, pos) is None else None
            if isinstance(expr, Star):
                cur = pos
                while True:
                    nxt = run(expr.body, cur)
                    if nxt is None:
                        return cur
                    if nxt == cur:
                        raise RuntimeError("zero-length expression under repetition")
                    cur = nxt
            raise TypeError(f"unknown expression type: {type(expr)!r}")

        result = run(Ref(self.start), 0)
        return result == len(text)

    def to_text(self) -> str:
        """Serialize to a conservative Ford-style PEG notation."""

        def quote(text: str) -> str:
            escaped = (
                text.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
            )
            return f"'{escaped}'"

        def render(expr: Expr, precedence: int = 0) -> str:
            # Higher number binds more strongly.
            if isinstance(expr, Epsilon):
                return "''"
            if isinstance(expr, Fail):
                return "!."
            if isinstance(expr, Literal):
                return quote(expr.text)
            if isinstance(expr, AnyChar):
                return "."
            if isinstance(expr, Ref):
                return expr.name
            if isinstance(expr, Star):
                inner = render(expr.body, 4)
                out = f"{inner}*"
                return f"({out})" if precedence > 4 else out
            if isinstance(expr, And):
                inner = render(expr.body, 3)
                out = f"&{inner}"
                return f"({out})" if precedence > 3 else out
            if isinstance(expr, Not):
                inner = render(expr.body, 3)
                out = f"!{inner}"
                return f"({out})" if precedence > 3 else out
            if isinstance(expr, SeqExpr):
                out = " ".join(render(part, 2) for part in expr.parts)
                return f"({out})" if precedence > 2 else out
            if isinstance(expr, Choice):
                out = " / ".join(render(alt, 1) for alt in expr.alternatives)
                return f"({out})" if precedence > 1 else out
            raise TypeError(type(expr))

        lines = []
        # Start rule first, then stable alphabetical order for reproducibility.
        order = [self.start] + sorted(name for name in self.rules if name != self.start)
        for name in order:
            lines.append(f"{name} <- {render(self.rules[name])}")
        return "\n".join(lines) + "\n"
