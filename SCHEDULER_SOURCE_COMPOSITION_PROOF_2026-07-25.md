# Ordinary source/scheduler composition proof

Date: 2026-07-25

Scope: the corrected 225-tape SG source, the certified Galil constant
`c_G=1,781,819,703`, and the compact period
`L=2c_G=3,563,639,406`.  This proof constructs a finite ordinary bounded-delay
input/output machine.  The final Hartmanis--Stearns speedup is treated in the
companion document.

## Theorem

There is an effectively generated deterministic ordinary multitape transducer
`M_sched` which:

1. emits exactly the output trace of Galil's abstract FAST/SLOW scheduler applied
   to the corrected SG source;
2. uses 295 ordinary work tapes;
3. has 1,653,051 factored finite-control states;
4. has 8,305,403 sparse transition rows;
5. performs at most

       K = 416,945,810,716

   ordinary transitions after reading one physical input symbol and before
   emitting that prefix's output and advancing to the next physical symbol.

No source-state/countdown Cartesian product is used.  Every one of the
6,502,172 source rows is transformed exactly once.

## 1. Work-tape layout

The 225 certified source tapes are retained verbatim.  The scheduler adds:

- twelve data tapes, one state-register tape, and one continuation tape for a
  strict append/read input history;
- 21 fixed one-cell source-state bit tapes;
- 32 fixed one-cell countdown bit tapes;
- one unary lag tape;
- one pending-output tape;
- one FAST/SLOW mode tape.

Thus the work-tape total is

    225 + 14 + 21 + 32 + 1 + 1 + 1 = 295.

The input tape is read-only and the output tape is one-way write-only; neither
is included in that work-tape count.

## 2. Representation invariant

At every active scheduler state (`SOURCE_DISPATCH`, a source-active state,
`CLOCK`, or `COMPLETE`):

1. the 225 source tapes and their heads are exactly the source-machine
   configuration after the source has processed through position `h1-1` and is
   working on position `h1`;
2. the 21-bit register is the little-endian encoding of the source finite state;
3. the input history represents every physical input symbol through position
   `h2`, with its logical reader scanning position `h1` and its writer just to
   the right of position `h2`;
4. the unary lag tape contains exactly `h2-h1` units;
5. the 32-bit countdown is the remaining number of counted source steps before
   the next speculative output deadline;
6. the mode tape records Galil's FAST or SLOW mode;
7. if the source has just entered `SOURCE_DONE_0` or `SOURCE_DONE_1`, the pending
   output tape contains the corresponding bit.

At `AWAIT_FAST` or `AWAIT_SLOW`, the machine is instead in the corresponding
post-output/pre-read boundary configuration: the input head already scans the
next physical cell, while the source and history configurations are left exactly
as they were at the emitted event.  Lemma 4.1 converts that boundary into the
active invariant after the next symbol is read.

The strict history zipper's proved refinement supplies item 3 using only
ordinary one-cell moves.  The lag tape makes head equality explicit:
`h1=h2` iff its head scans the bottom marker.  No unproved multihead-equality
oracle is used.

## 3. Row families

### Source dispatch

For each nonterminal source state `q`, one row reads its exact 21-bit encoding
and enters `SOURCE_ACTIVE(q)`.  The two terminal source states are handled by
`COMPLETE` and are never redispatched.

Count: `1,562,426-2 = 1,562,424` rows.

### Source lift

A certified source row

    (q, source reads) -> (q', source writes/moves)

is transformed into one row at `SOURCE_ACTIVE(q)`.  It performs the identical
source writes and moves, writes only changed source-state bits, and then:

- enters `CLOCK` when `q'` is nonterminal;
- writes the pending output and enters `COMPLETE` when `q'` is a source-done
  state.

Count: exactly `6,502,172` rows.  Product factor: exactly one.

### Input history

The already audited ordinary history machine contributes:

- 90,606 load-dispatch rows;
- 141,888 active worker rows;
- four continuation-dispatch rows.

Count: `232,498` service rows.

There are six call sites—four bit/mode-specific APPEND sites and two RIGHT
sites.  Each is expanded over the 1,268 reachable ready-state symbols.

Count: `6*1,268 = 7,608` call rows.

After a lagged RIGHT, 317 ready states encode current symbol 0 and 317 encode
current symbol 1.  These 634 exact rows set the next source entry state.

### Clock and terminal control

The 63-row exact binary countdown has one tick row.  Its 62 non-tick rows are
shared, while the tick row is split by FAST/SLOW mode, giving 64 rows.

Two equal-completion rows emit pending output 0 or 1, reset the clock, enter
FAST, and advance the physical input head.  One buffered-APPEND continuation
writes a new lag unit.

The complete row count is therefore

    6,502,172  source lifts
  + 1,562,424  source dispatch
  +   232,498  history service
  +     7,608  history calls
  +       634  lagged source selection
  +        64  clock
  +         2  equal completion
  +         1  buffered lag write
  = 8,305,403.

## 4. One-step simulation lemmas

### Lemma 4.1: physical read

In FAST mode, APPEND followed by RIGHT records the new physical bit, positions
the simulated reader on it, and installs the corresponding source entry state.
Lag stays zero.

In SLOW mode, APPEND records the new bit while the lag head moves to a virgin
cell; the continuation writes one lag unit.  The source state and simulated
reader do not move.

Thus one physical read preserves the representation invariant and implements
Galil's physical-head action.

### Lemma 4.2: source microstep

Exact 21-bit dispatch chooses the unique source state.  Determinism of the
certified source table chooses the unique matching lifted source row.  Its
projection on the first 225 tapes is precisely the original source transition,
and its source-register writes encode precisely the successor state.

Thus one dispatch/lift pair simulates exactly one source primitive transition.

### Lemma 4.3: completion

If lag is zero, `COMPLETE` emits the pending real source bit, resets the clock,
advances the physical input head, and enters FAST.

If lag is positive, the same caller row erases one unary lag unit and starts a
history RIGHT call.  The returned history state identifies the next buffered
bit, which selects `READ0` or `READ1`; the real source output for the already
speculated position is ignored.  Mode remains SLOW.

These are exactly Galil's equal and lagged completion branches.

### Lemma 4.4: countdown

The compact countdown rows partition every positive 32-bit value.  A non-tick
row decrements the value and resumes source dispatch.  At value one, the
mode-specific tick row reloads `L`, emits zero, advances the physical input
head, and enters or remains in SLOW.

This is exactly one counted scheduler source step.

### Composition theorem

Induction on ordinary transition segments between physical outputs, using
Lemmas 4.1--4.4, proves that the concrete machine and the abstract compact
scheduler have identical `(mode,h1,h2,clock)` states at corresponding
boundaries and emit identical output events.  Hence every speculative output is
exactly the one justified by the already proved Galil predictability theorem,
and every genuine output is the source output for the same prefix.

## 5. Bounded delay

The proved registered history costs are:

    APPEND <= 101,
    RIGHT  <= 113.

A direct read therefore costs at most `214`.  A buffered read costs at most
`101+1=102`, because the lag-head move is folded into the APPEND caller row and
the continuation writes the unit.

One counted source step costs at most:

- noncompletion: dispatch + source + clock = `3`;
- equal completion: dispatch + source + completion = `3`;
- lagged completion:

      dispatch + source + registered RIGHT + source-entry select + clock
      = 1 + 1 + 113 + 1 + 1
      = 117.

The clock permits at most `L=3,563,639,406` counted source steps after one
physical read.  Therefore

    K <= 214 + 117 L
      = 416,945,810,716.

Output emission and the physical input-head move occur in the equal-completion
or clock-tick row and are already included.

## 6. Finiteness and determinism

- Source dispatch guards are distinct complete 21-bit vectors.
- Lifted source rows inherit source determinism.
- History service and call rows are partitioned by exact component-state
  register symbols.
- The lag-zero and lag-positive completion guards are disjoint.
- Lagged source-selection rows are partitioned by exact ready states whose
  finite `current` field is 0 or 1.
- Compact countdown guards partition positive counter values; the sole tick
  guard is split by disjoint mode symbols.

All tape alphabets, state sets, and row families are finite and mechanically
enumerable.  Every row performs one simultaneous one-cell move per ordinary
work tape.

## Status

**Proved within the construction**

- exact factored row transformation;
- absence of source/countdown product;
- representation invariant;
- trace equivalence with abstract FAST/SLOW scheduling;
- bounded delay `K=416,945,810,716`;
- exact state, tape, and row inventories above.

**Computational evidence**

- exhaustive abstract-composition agreement for all short work/output traces
  used by the accompanying tests;
- literal generation and counting of all 240,740 non-source-dispatch/non-source
  rows;
- imported scheduler, source-bound, and corrected six-case regressions.

**Not claimed here**

- a conventional one-input-transition-per-symbol machine; that follows from
  the separate fixed-speedup application;
- a materialized sped-up transition table;
- the final PEG compilation.