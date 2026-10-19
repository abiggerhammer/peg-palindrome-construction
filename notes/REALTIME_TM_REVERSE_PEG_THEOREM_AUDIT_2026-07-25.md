# Audit and generic theorem: deterministic real-time multitape machines to PEGs for reversed languages

Date: 2026-07-25

## 1. Scope and claim boundary

This checkpoint audits the generic portion of the completed binary-even-palindrome construction. It separates the palindrome-specific source recognizer and scheduler from the language-independent scaffolding/PEG backend.

The status words in this document are literal:

- **Proved**
- **Proof sketch**
- **Computational evidence**
- **Conjectured**
- **Retracted**
- **Needs rechecking**

Nothing below claims peer review or external publication-level verification.

## 2. Audit verdict

### Proved

The following theorem holds under the conventional streaming real-time multitape-machine model defined in Section 4.

> **Real-time reversal theorem.** For every deterministic conventional real-time multitape Turing machine \(M\), one can effectively construct a finite ordinary parsing expression grammar \(G_M\) such that
> \[
> L(G_M)=L(M)^R.
> \]

A stronger bounded-delay block theorem also holds: a fixed finite number of ordinary work-tape transitions per physical input symbol can be compiled into a radius-two scaffolding automaton, and hence into an ordinary PEG for the reversed language.

The theorem is proved below rather than inferred from the palindrome tests.

### Proved

The palindrome dependency graph splits as follows.

Palindrome-specific:

1. corrected Seiferas--Galil controller;
2. checkpoint semantics and cleanup;
3. predictability bounds;
4. Galil scheduling;
5. source/scheduler composition and speedup;
6. the fact that the resulting bounded-delay machine recognizes even palindromes.

Generic:

1. persistent zipper/block representation of work tapes;
2. one-new-scaffold-node simulation;
3. radius-two locality;
4. one-use initial-state normalization;
5. total completion on the full formal neighbourhood domain;
6. Loff--Moreira--Reis scaffolding-automaton-to-PEG expansion.

Thus the generic theorem does not depend on any palindrome midpoint lemma, checkpoint argument, or six-case analysis.

## 3. Published bridge used

Loff, Moreira, and Reis prove that a language \(K\) has a PEG if and only if \(K^R\) is decided by a scaffolding automaton. Equivalently, any scaffolding automaton deciding \(L\) effectively yields an ordinary PEG recognizing \(L^R\).

Their sufficient-direction construction assumes, without loss of generality, that the initial state is used only at the beginning. Its finite nonterminal families are `State`, `Label`, `Neighbourhood`, `Path`, and `AutomatonAccepts`.

The present proof therefore has one machine-theoretic obligation: construct a finite total scaffolding automaton for \(L(M)\).

## 4. Conventional real-time machine model

### Definition

A deterministic conventional real-time \(m\)-tape machine is a tuple with:

- finite input alphabet \(\Sigma\);
- finite work alphabet \(\Delta_i\) on each tape, with blank \(\square_i\);
- finite state set \(Q\), initial state \(q_0\), and accepting set \(F\);
- a total transition function which, for each input symbol, current state, and tuple of scanned work symbols, performs exactly one transition: it changes state, writes one symbol on each work tape, and moves each work head left, right, or not at all.

The input symbol is supplied to the finite control once per transition. The input is not a separately revisitable tape. All work tapes are two-way infinite and initially blank, with their heads at cell zero. Acceptance is determined by the state after the last input symbol. This convention includes the empty input.

Partial machines can be totalized by adding a rejecting sink state, so totality is not a substantive restriction.

## 5. Radius-two zipper scaffolding construction

### 5.1 Finite tape representation

For each work tape, write its finite visited portion as a zipper
\[
(L,h,R),
\]
where:

- \(h\in\Delta_i\) is the symbol under the head;
- \(L\) is a finite stack of cells immediately to the left, nearest first;
- \(R\) is a finite stack of cells immediately to the right, nearest first;
- cells beyond the represented stacks are implicitly blank.

Explicit blank symbols are permitted inside \(L\) and \(R\); an extra marker \(\bot\) denotes an empty stack. This distinction is necessary because a visited blank cell is not the same structural position as the unvisited infinite blank tail.

### 5.2 Scaffold degree, radius, labels, and states

Use scaffold degree \(d=2m\) and radius \(k=2\). For tape \(i\), edge \(2i\) is its left-stack link and edge \(2i+1\) its right-stack link.

A normal node label stores, for every tape \(i\),
\[
(h_i,\operatorname{top}(L_i),\operatorname{top}(R_i)),
\]
where a top is in \(\Delta_i\cup\{\bot\}\). The full label alphabet is therefore finite.

The scaffold states are:

- a synthetic one-use initial state `INITIAL`;
- one normal state for each \(q\in Q\);
- a rejecting state `SINK`.

Add a distinguished sink label to the finite working alphabet.

### 5.3 Stack invariant

After reading a nonempty prefix \(x\), the current scaffold top encodes the exact machine configuration after \(x\).

For each represented stack \(S=s_1s_2\cdots s_r\):

- the current node's corresponding top field is \(s_1\), or \(\bot\) if \(r=0\);
- if \(r\ge2\), the corresponding edge points to a prior node whose same top field is \(s_2\);
- following that same edge repeatedly exposes \(s_3,s_4,\ldots\);
- if \(r\le1\), the corresponding edge is absent.

Only the first two stack symbols are needed to calculate a one-cell move, so the radius-two neighbourhood suffices.

### 5.4 One transition

Suppose the old machine transition writes \(w_i\) on tape \(i\).

#### Stay

The new scanned symbol is \(w_i\). Both stack tops remain unchanged. Copy both old stack edges by targeting the one-edge paths from the old top.

#### Move right

The new left stack is \(w_iL_i\). Therefore:

- the new left-top field is \(w_i\);
- if \(L_i\) was nonempty, the new left edge targets the old top by the empty path; otherwise it is absent.

The new scanned symbol is the old right top, or blank if the old right stack was empty. The new right stack is the tail of \(R_i\). Therefore:

- its new top is read from the label under the old right edge, or is \(\bot\) if no such node exists;
- its new edge targets the old two-step path `(right,right)` when that path exists, and is absent otherwise.

#### Move left

This is symmetric: push \(w_i\) onto the right stack and pop the left stack, using the empty path on the pushed side and the two-step `(left,left)` path on the popped side.

All target paths have length at most two. No self-edge is required.

### 5.5 Initial and malformed neighbourhoods

The initial scaffold consists of the single unlabelled base node with no edges. In state `INITIAL`, on the first input symbol, simulate one machine transition from \(q_0\) with every scanned symbol blank and both zipper stacks empty. Enter the resulting normal state and emit the corresponding normal label and edges. No transition ever returns to `INITIAL`.

For every other formal radius-two neighbourhood presented while in `INITIAL`, enter `SINK`.

For a normal state, reject malformed zipper neighbourhoods—such as an empty-stack marker paired with a present stack edge—by entering `SINK`. The sink loops on every input symbol and every formal neighbourhood, emits the sink label, and has no edges.

This defines a total transition function on the complete finite set \(Q'\times\Sigma\times N_2(d,\Gamma)\), not merely on reachable canonical neighbourhoods.

### 5.6 Correctness induction

### Proved

Base case: before any input, all tapes are blank and the finite control is \(q_0\). `INITIAL` is accepting exactly when \(q_0\in F\).

Induction step: assume the scaffold invariant after prefix \(x\). The radius-two neighbourhood supplies the old state, every scanned symbol, the tops of both stacks, and the second symbol of each nonempty stack. The total machine transition is therefore determined. The update rules in Section 5.4 are exactly the algebra of a zipper after write-and-move. Consequently the new node encodes the exact machine configuration after \(xa\), and the stack invariant is preserved.

Hence after every input \(x\), the scaffolding automaton is accepting if and only if \(M\) accepts \(x\). It decides \(L(M)\).

Applying the sufficient direction of the Loff--Moreira--Reis theorem gives an effectively constructible finite ordinary PEG for \(L(M)^R\).

This completes the proof of the real-time reversal theorem.

## 6. Bounded-delay block extension

### Theorem

### Proved

Let \(M\) be a deterministic streaming multitape machine with a fixed constant \(K\) such that, between two successive physical input boundaries, it performs at most \(K\) ordinary work-tape transitions, consumes exactly the current physical input symbol and no future symbol, and reaches a new boundary state. Then \(L(M)^R\) is PEG-recognizable.

### Proof

Choose a block width \(B\ge K\) and partition each work tape into globally aligned blocks of \(B\) cells. At a boundary, a scaffold node stores for each tape:

- the head offset in the current block;
- the current block;
- the nearest left and right blocks, or an empty-stack marker.

Two edges per tape represent the remaining block stacks exactly as in the cell zipper construction.

During at most \(K\le B\) moves, a head can inspect only the current block and its immediate left and right neighbours. If it finishes in the right neighbour, it cannot also have visited the left neighbour: after first reaching a left-neighbour cell, reaching a right-neighbour cell requires more than \(B\) further moves. The symmetric statement holds when it finishes left.

Thus one bounded simulation of the finite three-block window determines:

- the next boundary state;
- the modified current/adjacent blocks;
- which of the three old blocks contains the new head;
- new persistent block-stack edges, each targeting only the old top, a one-edge path, a two-edge path, or no node.

The block alphabet is finite because \(B\), the number of tapes, and every tape alphabet are fixed. As above, add a one-use initial state and a rejecting total sink for every malformed or unreachable formal neighbourhood. The reachable-configuration induction is identical to Section 5.6 at block granularity. The resulting finite radius-two scaffolding automaton decides \(L(M)\), and the published scaffolding-to-PEG theorem yields a PEG for \(L(M)^R\).

The conventional theorem is the special case \(K=B=1\).

## 7. Audit of the completed compiler artifacts

### Proved within the checked construction

The final palindrome indexed compiler repairs the two formal issues that matter to the generic theorem:

1. `INITIAL` is genuinely one-use and is never a normal transition result;
2. the transition oracle is total on the full formal radius-two neighbourhood domain, with malformed cases sent to an explicit rejecting sink.

The final indexed rule families match the published `State`, `Label`, `Neighbourhood`, `Path`, `Transition`, and `AutomatonAccepts` construction. All index domains are finite, so the indexed object is an effective finite abbreviation of an ordinary PEG.

### Computational evidence

Repository tests run during this audit:

- 2 bounded-delay macro differential tests passed;
- 4 indexed-expander/totality/LMR-fold tests passed;
- 1 full succinct-schema finiteness/radius test passed;
- 3 direct real-time and sparse-real-time differential tests passed.

An additional randomized audit generated 70 arbitrary total machines with one or two work tapes, four states, and a three-symbol work alphabet. The generated PEGs were compared with direct machine execution on 15,290 binary words. All comparisons passed.

These tests support the implementations; they are not the proof of Sections 5 and 6.

### Needs rechecking

The small literal block simulator duplicates `old.left_second` or `old.right_second` into a returned second-block field when the head finishes in an adjacent block. The true new second block on the popped side would be the old third block, which is represented by a two-edge scaffold path rather than present in the finite `TapeNeighborhood` record.

This appears to be a dead-field/interface defect rather than a language-correctness defect:

- emitted node labels use only offset, current block, left top, and right top;
- emitted edge targets use the correct two-edge path;
- the final indexed implementation explicitly treats that farther block as unknown and relies on the two-edge path;
- the returned second field is not used to construct the emitted label or target on that popped side.

Nevertheless, the literal helper should be clarified or repaired before treating its returned `IntervalResult.neighborhoods` as an exact standalone next-boundary snapshot.

## 8. Consequences for the CFL-versus-PEG program

### Proved

Let `DRTMT` be the class of languages decided by deterministic conventional real-time multitape machines. Then
\[
\operatorname{Rev}(\mathrm{DRTMT})\subseteq\mathrm{PEG}.
\]
More generally, the reversal of every deterministic fixed-bounded-delay streaming multitape language is in PEG.

Therefore any proposed CFL separator \(L\) is eliminated as soon as a deterministic real-time or fixed-bounded-delay recognizer is found for \(L^R\).

### Proved from known PEG closure results

The standard inherently ambiguous language
\[
A=\{a^i b^j c^k : i=j\text{ or }j=k\}
\]
is not a separator. It is the union of two deterministic context-free languages, and PEG languages contain the Boolean closure of the relevant deterministic context-free subclasses. This gives a concrete reason that inherent ambiguity alone is inadequate.

### Proved as a reduction of the positive program

Greibach constructed a hardest context-free language \(H\) such that every CFL is an inverse homomorphic image of \(H\) (with the conventional empty-word adjustment). Loff--Moreira--Reis observe that if any CFL lacks a PEG, then \(H\) lacks a PEG; equivalently, proving that \(H\) has a PEG proves that every CFL has a PEG.

Combining that observation with the real-time reversal theorem gives a single canonical sufficient target:

> If \(H^R\) is decidable by a deterministic real-time or fixed-bounded-delay multitape machine, then every context-free language is PEG-recognizable.

This does not assert that such a machine exists.

### Conjectured research direction

The next positive branch should attack \(H^R\) directly. Its block-and-semi-Dyck structure may expose enough witness information in the input to permit deterministic online verification even though the language is designed to represent arbitrary CFG derivations. The exact language definition must first be reconstructed cleanly from Greibach's paper or a reliable revised presentation; no machine claim should precede that step.

### Proved limitation of the negative branch

Failure to find a real-time machine, or even a proof that no such machine exists, would not prove non-PEG-recognizability. PEGs/scaffolding automata include languages for which neither direction has a strongly online multitape recognition algorithm. A separation must therefore establish an invariant of scaffolding automata or PEGs themselves, not merely a real-time lower bound.

## 9. Narrowed candidate criteria

A serious separator candidate should satisfy all of the following before substantial effort is invested:

1. It is not already covered by deterministic CFLs, regular closure, or their known Boolean closure inside PEG.
2. Its reverse has no known deterministic real-time or fixed-bounded-delay multitape recognizer.
3. Its apparent difficulty is not only CFG ambiguity or nondeterministic presentation.
4. The proposed obstruction is stated as a property of every scaffolding automaton, and is tested against the even-palindrome construction.
5. The proof does not rely only on generic linear-time or online-TM lower bounds.

The most credible negative direction remains a bounded-degree-DAG information invariant: formalize a notion of independent unresolved obligations that requires more than one bounded-degree node of fresh persistent structure per input symbol. This is currently only a research program, not a theorem.

## 10. Next exact tasks

1. Produce a small language-independent theorem certificate and reference implementation for the cell-zipper construction, separate from the palindrome repository.
2. Repair or document the dead second-block fields in the literal bounded-delay helper.
3. Extract a clean formal definition and grammar for Greibach's hardest CFL \(H\), including the empty-word convention and inverse-homomorphism theorem.
4. Reverse that definition and attempt a phase-by-phase deterministic bounded-delay recognizer.
5. In parallel, formulate a candidate scaffolding invariant in terms of fresh persistent obligations and try to falsify it on the palindrome scaffold before using it against any CFL.

## 11. Final status ledger

### Proved

- deterministic conventional real-time multitape language reversal is PEG-recognizable;
- deterministic fixed-bounded-delay streaming multitape language reversal is PEG-recognizable;
- the construction is finite, effective, radius two, one-node-per-symbol, total, and compatible with the published ordinary-PEG expansion;
- the palindrome proof splits cleanly into a language-specific front end and a generic backend;
- the canonical ambiguous union language above is already PEG-recognizable;
- a real-time recognizer for \(H^R\) would imply that every CFL is PEG-recognizable.

### Computational evidence

- all 10 selected repository tests passed when run separately;
- 70 additional randomized machines and 15,290 word comparisons passed.

### Conjectured

- \(H^R\) may admit a deterministic bounded-delay recognizer;
- a useful negative invariant may be expressible through bounded fresh persistent obligations.

### Needs rechecking

- exact clean transcription of Greibach's \(H\);
- the dead second-block fields in the small literal helper;
- independent proof audit and peer review of both the palindrome theorem and this generic extraction.

### Not proved

- every CFL is PEG-recognizable;
- any CFL is not PEG-recognizable;
- \(H\) or \(H^R\) is PEG-recognizable;
- any general reversal closure theorem for PEG languages.