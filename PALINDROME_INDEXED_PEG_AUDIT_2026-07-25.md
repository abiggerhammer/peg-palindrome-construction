# Indexed ordinary-PEG definition audit

Date: 2026-07-25

## Result

The full presentation is now an exact finite abbreviation of the ordinary
Loff--Moreira--Reis sufficient-direction grammar. It has only the standard
families `State`, `Label`, `Neighbourhood`, `Path`, `Transition`, and
`AutomatonAccepts`. Bounded-delay simulation is compile-time work and does
not occur as a PEG operator.

A synthetic `INITIAL` state is used only on the unlabelled base. Normal
states are `(boundary_state, output_bit)`, and a rejecting `SINK` completes
the transition function on every noncanonical member of the full finite
radius-two neighbourhood domain.

## Line-by-line correspondence

| LMR item | Indexed family |
|---|---|
| `State(q)` | `State[state]` |
| `Label(gamma)` | `Label[whole tagged block label]` |
| `Neighbourhood(N)` | `Neighbourhood[exact N_2 tree]` |
| `Path(p)` | `Path[path of length at most 2]` |
| `Transition(q,sigma,N)` | `&(sigma State(q)) &(sigma Neighbourhood(N))` |
| accepting rule | accepting states followed by `.*` |

The exact neighbourhood rule checks the root label, every present path,
the exact label at each present path, and every missing path. This is the
published construction rather than a new grammar operator.

## Selected full-machine rules

`Path_eps <- epsilon`

`State_INITIAL <- EOF`

The trivial unlabelled radius-two base neighbourhood also has the sole
alternative `EOF`.

### First physical symbol `0`

`Transition_4471056bd769a283 <- &('0' State_INITIAL) &('0' Neighbourhood_20c960abc079ad8e)`

This adds `Transition_4471056bd769a283` as an alternative of `State_q0_o0`.
The source branch is initial case 3 and has proved cost at most 2755, below scheduler c=1781819703;
there is no speculative tick, the emitted bit is 0, and the next normal
scheduler state is `(AWAIT_FAST,0)`.

### First physical symbol `1`

`Transition_d412fa6491c4e460 <- &('1' State_INITIAL) &('1' Neighbourhood_20c960abc079ad8e)`

This adds `Transition_d412fa6491c4e460` as an alternative of `State_q0_o0`.
The source branch is initial case 3 and has proved cost at most 2755, below scheduler c=1781819703;
there is no speculative tick, the emitted bit is 0, and the next normal
scheduler state is `(AWAIT_FAST,0)`.

## Finiteness and termination

Every work-tape alphabet is finite. The block width, tape count, state set,
degree, and radius are fixed integers. Therefore the whole-label alphabet,
the recursively defined radius-two neighbourhood set, the path set, and the
transition-index set are finite.

For each transition index, the compiler scans the finite 8305403-row
ordinary machine for at most 416945810716 primitive steps. It then emits
one finite scaffolding transition and folds it into the standard ordinary PEG
alternatives. Noncanonical indices take the constant rejecting sink transition.
Thus the nested generator terminates and prints a finite ordinary PEG.

## Claim boundary

The astronomical grammar text has not been physically printed. The finite domains,
total transition algorithm, standard rule templates, and selected concrete rules
are explicit and executable. The theorem is classified as proved within this
construction, not as independently reviewed or published.