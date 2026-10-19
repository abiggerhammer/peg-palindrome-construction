# Suggested X thread

Replace `REPO_URL` with your public GitHub URL, then post these as separate tweets.

**1/4** (250 chars)

I think I have a counterexample to Conjecture 7 of Loff–Moreira–Reis (JCSS 2020): the language of all binary even-length palindromes appears to have an ordinary PEG.

It's a constructive, AI-assisted proof candidate, not yet independently reviewed. 🧵

---

**2/4** (244 chars)

The route isn't a clever 5-line grammar. We use a corrected Seiferas–Galil palindrome recognizer, Galil scheduling, a fixed-bounded-delay multitape machine, and a radius-2 scaffolding automaton, then compile that to a PEG via Loff–Moreira–Reis.

---

**3/4** (263 chars)

The resulting PEG is finite, but astronomically large. Instead of printing it, we give an exact finite indexed generator that expands to standard PEG rules, plus proof checkpoints, certificates, and small-instance differential tests. No new recognition operators.

---

**4/4** (218 chars)

The July construction has internal tests, but no independent review or end-to-end Lean/Rocq proof. Please try to break the source-machine, scheduling, or PEG expansion arguments.

Proof, code, and audit notes: REPO_URL