# Seiferas--Galil extraction ledger

The full 1977 paper is now available and Section 7 has been specialized to
`r=s=0`.  See `seiferas_galil_specialization.md` for the derivation and
`sg_zero_ratio.py` / `sg_zero_ratio_machine.py` for executable audit models.

## Confirmed points

1. The parameters are explicitly **nonnegative**.  The paper itself states that
   `r=s=t=0` yields `{ww^R}`; the boundary case is therefore part of the theorem,
   not an inferred extension.
2. The paper's machine model is a multihead Turing machine.  It cites an
   effective, speed-preserving simulation by a one-head-per-tape multitape
   machine.
3. "Real time" means a constant bound on incremental work per newly received
   symbol.  Theorem 3 first gives an online algorithm satisfying the
   predictability condition and invokes Galil's lemma to obtain real time.
4. At `r=s=0`, `B2=B3`, `B4=2B3`, and `LEFT=2B3-RIGHT`.  `B3` and `B3'` are the
   centres of the longest and second-longest even palindromic suffixes.
5. The six update cases and all Fine--Wilf estimates specialize cleanly.  The
   case logic has been transcribed and exhaustively tested.
6. Corollary 3.2 obtains palindromes of both parities from the even-palindrome
   recognizer by the fixed homomorphism `h(a)=aa`.

## Remaining finite-program extraction

The semantic behavior of `RECOVER` and `LOCAL` is now implemented directly by
scanning the specialized Lemma 3.1 predicate.  This removes the palindrome
oracle from those branches, but the scan is deliberately unoptimized.  It must
still be replaced by a finite linear-time implementation of Lemma 3.2 to meet
the paper's scheduling bounds.

`BACKGROUND`, the Lemma 3.3 catch-up process used during case 5, remains
oracle-backed.

The dependencies to retrieve and transcribe are:

1. Fischer and Paterson, "String-matching and other products" (1974), used for
   linear-time period encoding and offline matching;
2. Galil, "String Matching in Real Time" (eventually JACM 28(1), 1981), for the
   predictability-condition conversion and related matcher machinery;
3. Fischer, Meyer, and Rosenberg, "Real-Time Simulation of Multihead Tape
   Units" (JACM 19(4), 1972), or the simpler Leong--Seiferas simulation.

## Lowering rule

Every remaining paper-level operation must become a finite macro with:

```python
@dataclass(frozen=True)
class Macro:
    name: str
    precondition: str
    postcondition: str
    deadline: int
    microsteps: tuple[PrimitiveStep, ...]
```

No final `palindrome.peg` will be emitted until every loop, arithmetic update,
parallel schedule, head reset, and offline scan has been expanded or compiled
mechanically into a finite transition table.
