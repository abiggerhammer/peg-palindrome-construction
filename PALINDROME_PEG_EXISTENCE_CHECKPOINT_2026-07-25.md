# Even-palindrome PEG existence checkpoint

Date: 2026-07-25

## Theorem established within the construction

Let

```text
EPAL = { w reverse(w) : w in {0,1}* }.
```

Exhaustively expanding `generated/palindrome_reverse.speg.json` by the finite
algorithms named in that file produces a finite ordinary parsing expression
grammar `G` over `{0,1}` such that

```text
L(G) = reverse(EPAL) = EPAL.
```

The word *ordinary* is literal: after expansion, `G` uses only terminals,
nonterminals, epsilon, sequence, prioritized choice, and-predicates,
not-predicates, and zero-or-more.  The compile-time bounded-delay evaluator,
block indices, and finite comprehensions are not operators of `G`.

This is classified as **proved within the checked construction**.  It has not
received independent external review, and the astronomical concrete grammar
text has not been physically printed.

## 1. Input machine

The input to this final compiler stage is the already certified ordinary
bounded-delay machine obtained by composing:

1. the corrected Seiferas--Galil zero-ratio source machine;
2. the compact Galil FAST/SLOW scheduler;
3. the ordinary scheduler/source storage and input buffer.

Its fixed inventory is:

```text
work tapes                  295
finite-control states       1,653,051
sparse ordinary rows        8,305,403
bounded delay K             416,945,810,716 transitions/input
block width B               2^39 = 549,755,813,888 cells
```

Thus `B >= K`.

## 2. Exact scaffolding automaton

For each work tape, one scaffold label stores:

- the head offset in its aligned `B`-cell block;
- the complete current block;
- the top block, or emptiness, of the left persistent block stack;
- the top block, or emptiness, of the right persistent block stack.

There are two scaffold edges per tape, so

```text
degree = 2 * 295 = 590.
```

The automaton uses radius two.

### Locality lemma

During one physical-input interval a work-tape head makes at most `K <= B`
unit moves.  Starting inside one aligned `B`-cell block, it can therefore visit
only its current block and the immediately adjacent left and right blocks.

If it finishes in the right block, it cannot also have visited the left block:
that would require strictly more than `B` head moves.  The symmetric statement
holds when it finishes in the left block.  Hence every changed block can be
stored in the new node, while every unchanged persistent tail is addressed by
a path of length at most two.

### State normalization and totality

The scaffolding state set is the finite disjoint union

```text
{INITIAL}
  union ({AWAIT_FAST, AWAIT_SLOW} x {0,1})
  union {SINK}.
```

`INITIAL` occurs only at the unlabelled base and is never an outcome of the
transition function.  This makes the one-use initial-state normalization
explicit.

The finite working alphabet is

```text
CanonicalLabel union {SINK_LABEL}.
```

The transition function is defined on the complete formal radius-two
neighbourhood domain, not only on reachable canonical snapshots.  A canonical
snapshot is simulated for at most `K` ordinary transitions.  Every malformed,
noncanonical, or otherwise unreachable neighbourhood goes to the fixed
rejecting `SINK` state with `SINK_LABEL` and no outgoing scaffold edges.
Therefore the scaffolding transition function is total.

## 3. Effective finiteness

Every tape alphabet is supplied by an exact finite enumerator.  In particular,
the source-fabric enumerator is run only after all 2,444 registered continuation
symbols have been allocated; the continuation tape has cardinality 2,445
including blank.

Every remaining domain has an explicit finite enumeration:

- a block is a fixed-length vector over one finite tape alphabet;
- a canonical tape label is a finite product of an offset and three block
  options;
- a whole label is the finite product over 295 tapes and one output bit;
- `N_0`, `N_1`, and `N_2` are generated recursively by the formal finite
  neighbourhood definition;
- paths are the 348,691 strings over 590 edges of length at most two;
- transition indices are the finite product
  `State x {0,1} x N_2`.

For a completely mechanical enumeration, a length-`B` block over an alphabet
of cardinality `m` may be enumerated by counting from `0` to `m^B-1` in base
`m`.  Nested mixed-radix counters enumerate products and vectors; tagged
counters enumerate finite sums.  This gives a terminating generator without
assuming that its output is practically writable.

For each transition index, the compile-time oracle has two nested finite
bounds:

1. at most `K` simulated primitive steps;
2. at most 8,305,403 streamed sparse rows inspected per primitive step.

The construction is grotesquely expensive, but effective and finite.

## 4. Exact ordinary-PEG expansion

The full schema now contains exactly the rule families used in the sufficient
direction of the scaffolding-automaton theorem:

```text
State(q)
Label(gamma)
Neighbourhood(N)
Path(p)
Transition(q, sigma, N)
AutomatonAccepts
```

For every transition index,

```text
Transition(q,sigma,N)
  <- &(sigma State(q)) &(sigma Neighbourhood(N)).
```

The transition is added as an alternative of:

- `State(delta_state(q,sigma,N))`;
- `Label(delta_label(q,sigma,N))`;
- each `Path(p)` whose first edge is retained by the new scaffold node.

`Neighbourhood(N)` is expanded into the finite conjunction of:

- the exact root label;
- existence tests for every present path;
- nonexistence tests for every missing path;
- the exact label at every present node through radius two.

`Path(epsilon) <- epsilon`.  The unlabelled base neighbourhood and the unique
initial state each receive their EOF alternative.  The start expression is the
choice of accepting-state predicates followed by `.*`.

No `MacroGate`, field selector, block-cell operator, circuit gate, or other new
recognition primitive occurs in the full schema.

## 5. Why the PEG recognizes the desired language

The exact block construction simulates one physical-input interval of the
bounded-delay machine per scaffold node.  By induction on the input length,
the scaffolding state, whole label, and persistent edges encode precisely the
machine's boundary configuration and output bit after each prefix.
Consequently the scaffolding automaton decides `EPAL`.

The sufficient direction of the Loff--Moreira--Reis characterization compiles
a scaffolding automaton deciding a language `L` into a PEG recognizing
`reverse(L)`.  Applying that finite rule construction to the automaton above
gives a PEG for `reverse(EPAL)`.  Since even palindromes are invariant under
reversal, this is `EPAL` itself.

## 6. On-demand expansion audit

`indexed_block_macro_expander.py` materializes selected standard rules and
computes selected finite delta entries.  `lmr_rule_expander.py` independently
implements the standard rule contribution formulas used by the literal reduced
backend.  `audit_palindrome_indexed_peg.py` expands and records representative
full-machine rules, including the two initial-symbol transition predicates.

The audit found and repaired two formal defects in the earlier checkpoint:

1. the former initial state could be re-entered, contrary to the normalization
   assumed by the published construction;
2. the schema ranged only over canonical reachable neighbourhoods rather than
   the complete finite formal radius-two neighbourhood domain.

The final version uses a unique one-use `INITIAL` state and explicit rejecting
sink completion over the full domain.

## 7. Validation ledger

Confirmed in this checkpoint:

```text
5  indexed-expander and full-schema tests
7  literal bounded-delay/scaffolding/PEG differential tests
18 scheduler/source composition and parameter tests
--
30 selected tests passed, 0 failed
```

The reduced literal backend checks, for finite machines and bounded binary
inputs,

```text
compiled_peg.recognize(reverse(x)) == machine.run(x).
```

Additional checks cover exact neighbourhood predicates, total sink completion,
unique initial-state behavior, exact LMR transition folding, exact registered
source alphabets, and deterministic artifact regeneration.

## 8. Deterministic artifacts

File SHA-256 values:

```text
palindrome_reverse.speg.json
  7e3f7cab9af2c53b679b8da3ac486c6993824a939c4d689f3e37f9718c20f8f9

palindrome_peg_compiler_certificate.json
  b3d5281635ff12e85d4b3f30f3b3e38bfb3a4749ddd6339ca9f815cbe40fc089

palindrome_indexed_rule_audit.json
  215894eb65e4544401304b6747e9fa5d97134a96ad9709e467c77064207b056e

PALINDROME_INDEXED_PEG_AUDIT_2026-07-25.md
  ad6851b1aff201a31b530a8073b075ead54ac798931b26872e559bb90f66e2fc
```

The schema's embedded canonical digest, which excludes its own digest field,
is:

```text
2d208065f425c2c6415223d80e7ead4104e5fbf556e656d4b28d9b4f5de7ed0c
```

## 9. Claim boundary

### Proved within the checked construction

- effective finiteness of the indexed presentation;
- exact total radius-two scaffolding automaton;
- standard ordinary-PEG expansion algorithm;
- reduced-machine literal differential correctness;
- existence of a finite ordinary PEG recognizing all binary even palindromes.

### Computational evidence

- the 30 selected regression tests;
- representative full-machine rule expansions;
- finite bounded semantic witnesses for the first input symbol;
- deterministic regeneration and hash agreement.

### Not claimed

- physical printing of the full grammar text;
- a remotely practical exhaustive run of the full generator;
- independent external verification;
- peer-reviewed or publication-level confirmation;
- resolution of the broader question whether every context-free language has a
  PEG.

The appropriate next scientific step is an independent proof audit of this
checkpoint before using the palindrome result as a settled lemma in the larger
CFL-versus-PEG program.