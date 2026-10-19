# Why would an enormous PEG for palindromes matter?

**A short introduction for readers who know some programming or formal languages but have not studied PEG expressiveness.**

> **Research status (October 2026):** This repository contains an AI-assisted **constructive proof candidate**, not an independently accepted theorem. It claims that a finite *ordinary* parsing expression grammar recognizes **every even-length binary palindrome**. The mathematical argument still needs independent audit.

## What's the actual question?

A **palindrome** reads the same forward and backward. This project uses just the alphabet `{0,1}`, and considers palindromes of **even length**:

| In the language | Not in the language |
| --- | --- |
| `""` (empty string), `00`, `11`, `0110`, `1001` | `0`, `01`, `010`, `0011` |

Formally, the language is

```text
EPAL = { w reverse(w) : w is any finite binary string }.
```

This language has a tiny **context-free grammar** (CFG):

```text
E → ε | 0 E 0 | 1 E 1
```

Here `ε` means the empty string. The rules build a palindrome by adding matching bits to both ends. For example, `0110` comes from `0 (1 ε 1) 0`.

So **recognizing even palindromes with a CFG was never the open problem**. The question was whether a **parsing expression grammar** (PEG) can recognize *exactly the same set of complete inputs*.

## Why isn't a PEG just a CFG with different punctuation?

A CFG offers alternatives: `A → B | C` permits either derivation. A PEG uses **ordered choice**: `A <- B / C` tries `B` and uses `C` only if `B` fails. A successful inner parsing expression is not generally reconsidered merely because an outer expression later fails.

That operational distinction matters even if the rules *look* the same. For example, simply transliterating the CFG as

```peg
Start <- E !.
E     <- '0' E '0' / '1' E '1' / ''
```

does **not** recognize all even palindromes with ordinary PEG semantics: on `0000`, an inner `E` can successfully consume a shorter prefix, leaving the outer match unable to finish; the successful inner parse is not revisited to try a different split. The `!.` in `Start` requires end of input, so this matters for *whole-string* recognition.

This **doesn't** mean PEGs have no way to recognize the language. PEGs also support lookahead predicates, and their expressive power is surprisingly subtle. It means that copying an elegant CFG is not enough to establish a PEG construction.

## Why was this a conjecture?

In *The Computational Power of Parsing Expression Grammars* (JCSS 2020), Bruno Loff, Nelma Moreira, and Rogério Reis developed a mathematical model called a **scaffolding automaton** and related it to PEG expressiveness.

They demonstrated PEGs for some unexpectedly complex languages, including **palindromes of restricted lengths** (notably a power-of-two family). But recognizing *every* even-length binary palindrome was unresolved. Their **Conjecture 7** says that `EPAL` has **no** PEG.

The construction in this repository claims the opposite. **If every step is correct, one counterexample is enough to refute that conjecture.** It would not, by itself, settle the larger question of whether *every* context-free language is PEG-recognizable.

## How does the proposed construction work?

The idea is **not** to find a short, clever palindrome grammar. It's to start with an automaton that recognizes the language and use the Loff–Moreira–Reis characterization to compile it into an ordinary PEG.

```text
Even-palindrome recognizer
    ↓  Corrected Seiferas–Galil source machine
Uniformly scheduled computation
    ↓  Galil scheduling; bounded work per input symbol
Finite scaffolding automaton
    ↓  Stores bounded tape blocks and persistent history links
Ordinary PEG
    ↓  Loff–Moreira–Reis rule construction
All even-length binary palindromes (claimed)
```

Here is the crucial bridge: the Loff–Moreira–Reis construction turns a scaffolding automaton for a language `L` into a PEG for its **reversal**, `reverse(L)`. But reversing an even palindrome leaves it unchanged:

```text
reverse(EPAL) = EPAL.
```

So, **if** the specialized machine really decides `EPAL`, **if** the bounded-delay scheduling and scaffold simulation are correct, and **if** the published scaffolding-to-PEG expansion has been implemented faithfully, the result is a PEG for `EPAL`.

The full technical argument is in [PROOF_OVERVIEW.md](PROOF_OVERVIEW.md).

## How can the grammar be finite but unimaginably large?

*Finite* does not mean *feasible to print or run*.

The recorded construction has **295 work tapes**, a bound of **416,945,810,716 primitive steps per input symbol**, and a fixed block size of `2^39` tape cells. These are **constants** in the construction, however terrible they are.

The repository therefore provides an **exact indexed specification**, finite enumeration procedures, rule expanders, proof checkpoints, and selected concrete expansions. It does **not** contain the physically printed, fully expanded PEG, which would be astronomically large.

There is no special-purpose palindrome operator hidden in the claimed final grammar. The compile-time generators may simulate machines and manipulate blocks, but the output grammar is claimed to use only **ordinary PEG constructs**: terminals, nonterminals, empty expressions, sequence, ordered choice, lookahead predicates, and repetition.

Whether that expansion is *fully justified* is itself an important audit question. This is an **existence claim**, not a proposal for a practical palindrome parser.

## What has actually been checked?

The release includes source code, written arguments, machine-readable artifacts and checksums, and tests on **selected and reduced cases**. GitHub Actions checks the archived artifact hashes and runs a small smoke-test selection.

That is valuable evidence about **reproducibility and implementation consistency**, but it is **not** a universal proof of the mathematical claim. Neither the complete enormous PEG nor its behavior on every input has been exhaustively executed. The proof has **not** been peer-reviewed or independently verified in a proof assistant.

The construction's internal audit also uncovered and repaired two issues: reuse of the initial state and a transition definition that initially omitted malformed formal neighborhoods. They deserve independent rechecking.

See [AUDIT_STATUS.md](AUDIT_STATUS.md) for exactly what has and has not been verified.

## Want to try to break it?

That is the purpose of publishing this repository. Useful criticisms are **specific counterexamples, missing hypotheses, or invalid inference steps**. In particular:

1. **Recognizer correctness:** Does the source machine accept exactly the even-length binary palindromes, including the empty string, and reject every other input?
2. **Scheduling:** Does the source machine really admit the claimed input-independent bound on work between input symbols?
3. **Scaffold simulation:** Do the block-locality and persistent-history arguments work at every boundary, and is the transition function total on *all* formal radius-two neighborhoods?
4. **PEG expansion:** Does the finite indexed generator really implement exactly the ordinary Loff–Moreira–Reis rules, including lookahead, reversal, initial-state, and end-of-input conventions?

Please cite the file and lemma involved when reporting a suspected defect. A failing reduced example or an explicit malformed neighborhood would be especially helpful.

**Reading route:** start with [PROOF_OVERVIEW.md](PROOF_OVERVIEW.md), then [PALINDROME_PEG_EXISTENCE_CHECKPOINT_2026-07-25.md](PALINDROME_PEG_EXISTENCE_CHECKPOINT_2026-07-25.md), then [PALINDROME_INDEXED_PEG_AUDIT_2026-07-25.md](PALINDROME_INDEXED_PEG_AUDIT_2026-07-25.md). The [README](README.md) links the remaining source proofs, tests, and generators.

**Original paper:** B. Loff, N. Moreira, R. Reis, [*The Computational Power of Parsing Expression Grammars*](https://doi.org/10.1016/j.jcss.2020.01.001), *Journal of Computer and System Sciences* 111 (2020), Conjecture 7 and the scaffolding-automaton characterization. [Preprint](https://arxiv.org/abs/1902.08272).

**Authorship and provenance:** This research candidate was developed with AI assistance under human research direction. The proof has not yet been independently validated.
