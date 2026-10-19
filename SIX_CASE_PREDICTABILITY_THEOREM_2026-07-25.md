# Explicit six-case source predictability theorem

Date: 2026-07-25

Scope: corrected `r=s=0`, `c=16` Seiferas--Galil ordinary source machine,
from `READ0`/`READ1` through `SOURCE_DONE_0`/`SOURCE_DONE_1`.  Galil's
fast/slow scheduler is not included in `need`.

## Theorem

Let

    j = B(ua)-B(u).

For the even-palindrome completion language, the exact availability increment
is

    avail(u,a) = 2j-1.

The corrected source machine satisfies, for every prefix `u` and next bit `a`,

    need(u,a) <= 947906*avail(u,a) + 1782767609.          (1)

The constants are conservative structural bounds tied to the generated
ordinary microprograms.  They are not claimed optimal for the underlying
algorithm.

## Proof

The proved primitive case bounds are:

| case | primitive source bound |
|---|---:|
| 1 | `1433` |
| 2 | `264841*j` |
| 3 | `891977*j` |
| 4 | `1468` |
| 5 | `1781819703` |
| 6 | `1895812*j` |

Cases 1, 4, and 5 have `j=0`, hence `avail=-1`.  Cases 2, 3, and 6
have `j>=1`.

Set

    C = ceil(1895812/2) = 947906.

This is the smallest integer coefficient supported by the current case-6
certificate.  Set

    D = C + 1781819703 = 1782767609.

For cases 1, 4, and 5, the right-hand side of (1) is

    -C + D = 1781819703,

which dominates all three constant bounds and meets the certified case-5
bound exactly.

For cases 2, 3, and 6,

    C(2j-1)+D
      = 1895812*j + 1781819703,

which dominates `264841*j`, `891977*j`, and `1895812*j` for every
`j>=1`.  This proves (1).

## Dependency ledger

Imported proved results:

- `CheckpointCorrect`;
- producer-paid checkpoint lifecycle bounds;
- `BackgroundUnitBound` and `BackgroundCatchUp`;
- case-6 outstanding-plus-fresh bound;
- cases 1--4 primitive bounds;
- specialized outer case-3 `4j`-window lemma;
- exact identity `avail=2j-1`.

No scheduler theorem or speculative-zero correctness is assumed here.