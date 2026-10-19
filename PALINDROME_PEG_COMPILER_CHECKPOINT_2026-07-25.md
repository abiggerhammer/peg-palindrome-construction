# Symbolic block-macro PEG compiler checkpoint

Date: 2026-07-25

## Scope

This checkpoint starts from the certified factored ordinary bounded-delay
machine obtained after:

- the corrected six-case Seiferas--Galil source construction;
- `CheckpointCorrect`;
- all six primitive predictability bounds;
- Galil FAST/SLOW scheduling;
- ordinary source/scheduler composition; and
- the 39-layer fixed-speedup theorem application.

The scheduled machine has 295 work tapes, 1,653,051 finite-control states,
8,305,403 sparse row-family instances, and certified delay

    K = 416945810716

ordinary transitions per physical input symbol.  The selected macro capacity is

    B = 2^39 = 549755813888 >= K.

The goal of this stage is to compile that machine without enumerating the
astronomical Hartmanis--Stearns paired alphabet.

## 1. Concrete bounded-delay compiler

`bounded_delay_macro_compiler.py` implements a literal backend for finite small
machines.

Each ordinary tape is partitioned into globally aligned blocks of width `B`.
At every physical-input boundary, one scaffold label records, per tape:

1. the head offset in the current block;
2. the complete current block;
3. the nearest explicit block on the left, or the blank-tail marker;
4. the nearest explicit block on the right, or the blank-tail marker.

Two scaffold edges per tape retain the rest of the persistent left and right
block stacks.

The literal backend:

- enumerates all finite boundary neighbourhoods;
- simulates one complete bounded-delay interval;
- emits a radius-two symbolic scaffolding automaton; and
- invokes the existing `compile_to_peg` backend to emit an ordinary PEG for the
  reverse language.

The enumeration is deliberately guarded by `max_transitions`; it is a proof and
differential-test backend, not the representation used for the full machine.

## 2. Block-locality lemma

Let a tape head begin at an arbitrary offset in an aligned block of width `B`.
During at most `B` ordinary unit moves, it cannot leave the union of:

- the block immediately to the left;
- its initial block; and
- the block immediately to the right.

This proves that a three-block finite neighbourhood determines the entire next
physical-input interval.

A second observation gives radius two.  If the head finishes in the right
neighbour, reaching that block and later visiting the left neighbour would
require more than `B` moves; symmetrically for a final left-neighbour position.
Thus, when the current block shifts by one, the untouched opposite stack can be
reused and the newly exposed stack top is reachable through at most two old
edges.  One new scaffold node therefore stores the complete updated tape
snapshot.

For 295 tapes the resulting scaffold has:

    degree = 2*295 = 590
    radius = 2
    path predicates = 1 + 590 + 590^2 = 348691.

## 3. Symbolic full-machine compiler

`succinct_block_peg.py` defines a finite indexed presentation of an ordinary
PEG.  `compile_palindrome_succinct_peg.py` instantiates it for the full
palindrome machine and writes:

- `generated/palindrome_reverse.speg.json`;
- `generated/palindrome_peg_compiler_certificate.json`.

The presentation contains nine finite rule families:

1. `State`;
2. `OffsetBit`;
3. `CurrentBlockCell`;
4. `SideTopEmpty`;
5. `SideTopCell`;
6. `Path`;
7. `MacroGate`;
8. `MacroTransition`;
9. `AutomatonAccepts`.

The indexed domains are all finite.  The immense block-cell families are
retained as integer-indexed families instead of being physically written.  A
literal expansion would contain at least

    3 * 295 * 2^39 = 486533895290880

indexed block-cell fields before accounting for symbol values and macro gates.

## 4. Symbolic macro closure

The interval transformer is represented by an absorbing deterministic
repeated-square closure.

- Layer 0 is the exact sparse ordinary one-transition row-family oracle named by
  `generated/scheduled_composition_row_family_manifest.json`.
- Layer `i+1` composes layer `i` with itself.
- Reaching the next physical-input boundary is absorbing: the unique boundary
  state, emitted bit, tape blocks, and head positions remain unchanged for the
  unused macro capacity.
- Layer 39 therefore represents exactly one physical-input interval because
  `2^39 >= K`.

This is equivalent to applying the symbolic 39-layer speedup, but it avoids
constructing any paired-symbol alphabet.

## 5. Existing PEG backend improvement

`compile_sa_to_peg.py` previously generated whole-label rules for every output
label even when no guard ever tested whole-label equality.  That defeated
field factoring.

It now creates `Label_*` nonterminals only for labels actually mentioned by a
`LabelIs` guard.  Field predicates continue to be generated exactly as before.
The existing ordinary compiler regressions remain green.

## 6. Validation

Literal differential tests compile reduced bounded-delay machines all the way
to ordinary PEGs and compare:

    PEG(reverse(word)) == direct_machine(word)

for every tested binary word.  The tests exercise:

- left and right aligned-block crossings;
- two-transition physical-input intervals;
- persistent stack push/pop in both directions;
- initial and subsequent scaffold nodes;
- acceptance by the last emitted bit.

Compiler-focused tests:

    8 passed

Scheduler/source supporting tests:

    19 passed

Total selected tests in this checkpoint:

    27 passed, 0 failed.

The full indexed schema and certificate were generated twice and were
byte-for-byte identical.

File SHA-256 values:

    generated/palindrome_reverse.speg.json
      3043eda7b34bf6aa6c01fbd8fbd3ae1411f0a5c1a9cb5e9ed336e5ee28597a0b

    generated/palindrome_peg_compiler_certificate.json
      b01fd02a73f2c520bc7da4eadf1768fc5c9fa411f63fb5d10f08950f822e1dad

The grammar object's canonical pre-embedding digest is:

    6f465b6224c50915862215e2b54260424d97c6ce5e761a382720f10a266062a4

## 7. Status ledger

### Proved within this construction

- the aligned three-block locality lemma;
- the one-new-node/radius-two persistent update lemma;
- correctness of the concrete bounded-delay-to-scaffold construction;
- correctness of its composition with the existing scaffold-to-PEG compiler;
- finiteness of every index domain in the full rule-family presentation;
- exact sufficiency of 39 absorbing squaring layers given the certified delay.

### Computational evidence

- literal ordinary-PEG differential tests on the reduced machines;
- deterministic full-schema regeneration;
- unchanged scheduler/source and ordinary compiler regressions.

### Constructively specified but still requiring independent audit

- the full indexed `MacroGate` expansion against the exact formal definition of
  a Loff--Moreira--Reis scaffolding automaton;
- the claim that the indexed rule-family presentation is a completely explicit
  finite abbreviation of the corresponding ordinary PEG under the intended
  expansion convention.

### Not claimed

- physical materialization of the astronomical ordinary PEG text;
- publication-level resolution of the open palindrome-PEG question;
- the broader conjecture that the reverse of every deterministic real-time
  multitape language is PEG-recognizable.

## 8. Next exact task

Audit the indexed presentation line by line against Definition 13/14 and the
sufficient direction of Theorem 16 in Loff--Moreira--Reis.  In parallel, add an
on-demand indexed-rule expander which emits and checks selected concrete
ordinary PEG rule bodies from the full schema.  Only after that audit should the
schema be promoted from a compiler checkpoint to an explicit palindrome-PEG
result.