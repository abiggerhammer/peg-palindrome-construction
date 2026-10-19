# Next research steps

## Construction status

The corrected Seiferas--Galil source, checkpoint semantics, timing bounds,
predictability theorem, Galil scheduler, ordinary scheduler/source composition,
fixed speedup, radius-two block scaffolding construction, and standard
scaffolding-to-PEG expansion have all been discharged within the workbench.

`PALINDROME_PEG_EXISTENCE_CHECKPOINT_2026-07-25.md` records the resulting
internal theorem: there is an effectively generated finite ordinary PEG for the
binary even-palindrome language.  The full text is astronomical and has not
been printed.

## Immediate scientific priority

1. Perform an independent proof audit of the complete checkpoint, with special
   attention to:
   - the bounded-delay block locality and persistent edge update;
   - total decoding of canonical neighbourhoods and sink completion;
   - exact correspondence with the sufficient direction of
     Loff--Moreira--Reis Theorem 16;
   - the reversal convention and acceptance rule.
2. Reproduce the reduced literal differential tests from a clean checkout and
   independently regenerate all certificate hashes.
3. Seek a second implementation of the finite indexed expander or a proof
   assistant formalization.

## Broader PEG program

Only after that audit should the palindrome theorem be treated as stable input
to the larger CFL-versus-PEG investigation.  The next target remains
Greibach's language H and related separation strategies.  The workbench does
not establish that every context-free language is PEG-recognizable, nor a
context-free counterexample.
