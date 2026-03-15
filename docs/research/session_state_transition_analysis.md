# Session State Transition Analysis

## 1. Scope

Pairs analyzed:

- `EURUSD`
- `GBPUSD`
- `USDJPY`

Timeframe:

- `15m` bars aggregated into completed FX sessions

Sample period:

- `2018-01-01 22:00:00+00:00` through `2024-12-31 21:45:00+00:00`

Session-state representation:

For each completed `asia`, `london`, and `new_york` session, R6 constructs a compact session-state record containing:

- pair
- session date
- session name
- session return
- session absolute return
- session range
- session direction
- time-aware volatility regime from R3
- range regime from R2 normalization
- directional efficiency ratio
- close location value
- dominant structural breach classification within the session:
  - `none`
  - `breakout`
  - `sweep`
- dominant breach direction
- dominant breach magnitude bucket

Outputs:

- `outputs/diagnostics/session_state_transitions/session_state_inventory.csv`
- `outputs/diagnostics/session_state_transitions/two_session_transition_summary.csv`
- `outputs/diagnostics/session_state_transitions/three_session_pattern_summary.csv`
- `outputs/diagnostics/session_state_transitions/next_session_outcomes_by_pattern.csv`
- `outputs/diagnostics/session_state_transitions/pair_transition_comparison.csv`
- `outputs/diagnostics/session_state_transitions/transition_pattern_notes.json`

## 2. Why R6 Exists

Earlier reset phases established that:

- raw session summaries are not enough
- raw structural breach labels are not enough
- context matters

R6 asks a stricter question:

what happens when one session state flows into the next, and what does that imply for the session after that?

This phase therefore studies:

- two-session transitions such as `asia -> london` and `london -> new_york`
- three-session sequences where the current session state is used to evaluate the next session outcome

The goal is not to define strategies. It is to test whether useful structure appears only once the market is viewed as a sequence of states rather than as isolated sessions.

## 3. Two-Session Transition Findings

### Baseline pair comparison

At the broadest level:

- `asia -> london` remains close to neutral in all three pairs:
  - `EURUSD` current-session continuation `0.4846`
  - `GBPUSD` current-session continuation `0.5149`
  - `USDJPY` current-session continuation `0.5008`
- `london -> new_york` is still the clearest carry transition:
  - `EURUSD` next-session continuation `0.6118`
  - `GBPUSD` next-session continuation `0.6015`
  - `USDJPY` next-session continuation `0.6821`

Interpretation:

- the direct `asia -> london` handoff is still not a generic directional edge
- the strongest sequence effect remains `london -> new_york`, especially in `USDJPY`

### Asia -> London

Coarse range-regime results:

- `EURUSD`
  - `normal -> expanded`: continuation `0.4369`, reversal `0.5631`
  - `compressed -> expanded`: continuation `0.4786`, reversal `0.5214`
- `GBPUSD`
  - `normal -> expanded`: continuation `0.5158`, reversal `0.4842`
  - `compressed -> expanded`: continuation `0.4887`, reversal `0.5113`
- `USDJPY`
  - `expanded -> expanded`: continuation `0.5603`, reversal `0.4397`
  - `compressed -> normal`: continuation `0.5622`, reversal `0.4378`

Interpretation:

- `asia compression -> london expansion` does happen often enough to study, but it is not uniformly continuation-friendly
- `EURUSD` still decays more than it carries
- `USDJPY` is more stable under expansion chains than the European pairs

### London -> New York

This is where the most useful multi-session structure appears.

Coarse next-session outcomes by London state:

`EURUSD`:

- London `expanded up` -> New York continuation `0.6385`
- London `expanded down` -> New York continuation `0.6696`

`GBPUSD`:

- London `expanded up` -> New York continuation `0.6184`
- London `expanded down` -> New York continuation `0.6809`

`USDJPY`:

- London `expanded up` -> New York continuation `0.7891`
- London `expanded down` -> New York continuation `0.7195`

Interpretation:

- expanded London states matter much more than raw London direction alone
- `USDJPY` carries directional state through the London -> New York boundary more cleanly than `EURUSD` or `GBPUSD`
- the European pairs still show carry, but it is notably weaker

## 4. Three-Session Pattern Findings

The three-session layer uses:

- previous session range regime
- previous session direction
- current session range regime
- current session direction
- current session dominant breach class

to measure the next-session outcome.

### Strongest pooled continuation patterns

The most robust high-sample continuation patterns are:

- `new_york -> asia` after expanded New York breakout states:
  - expanded down -> normal down breakout: continuation `0.7908`, sample `197`
  - expanded up -> expanded up breakout: continuation `0.7832`, sample `286`
  - expanded up -> normal up breakout: continuation `0.7783`, sample `203`
- `london -> new_york` after expanded London breakout states:
  - compressed down -> expanded down breakout: continuation `0.7476`, sample `104`
  - expanded down -> expanded up breakout: continuation `0.7468`, sample `154`
  - expanded up -> expanded down breakout: continuation `0.7083`, sample `169`

Interpretation:

- once the state model includes prior range and current expanded-directional structure, New York carry becomes much clearer
- the New York -> Asia transition also contains state persistence, but the repo’s main reset question still points more strongly to London -> New York

### Strongest pooled reversal patterns

The main reversal-heavy patterns are:

- `new_york -> asia` after compressed or normal New York states with direction change:
  - compressed up -> normal down breakout: reversal `0.8155`, sample `103`
  - expanded down -> normal up breakout: reversal `0.8158`, sample `114`
  - normal up -> normal down breakout: reversal `0.7724`, sample `123`
- `asia -> london` after expanded-up Asia states:
  - expanded up -> expanded up breakout: reversal `0.6105`, sample `173`

Interpretation:

- persistent directional chains are not the default
- transitions out of compressed or normal states often lose information quickly
- the useful structure is highly conditional on how the current session is expanding, not simply on whether the previous session was up or down

## 5. Pair Differences

### EURUSD

`EURUSD` remains the weakest carrier of state:

- `asia -> london` is still slightly reversal-dominated
- `london -> new_york` improves materially in expanded London states, but not enough to look like a clean standalone effect
- best `EURUSD` next-session continuation patterns still top out around the high-`0.7` range and rely on narrower expanded-breakout contexts

### GBPUSD

`GBPUSD` is similar to `EURUSD`, but slightly cleaner under some expanded chains:

- `london -> new_york` after expanded down London states reaches continuation `0.6809`
- London sweep sessions are also not obviously weaker than breakout sessions when flowing into New York:
  - breakout-dominant London sessions: next-session continuation `0.5976`
  - sweep-dominant London sessions: next-session continuation `0.6298`

### USDJPY

`USDJPY` is still the clear outlier:

- `london -> new_york` next-session continuation `0.6821` at baseline
- expanded-up London -> New York continuation rises to `0.7891`
- London sweep sessions carry into New York even better than London breakout sessions:
  - breakout-dominant London sessions: next-session continuation `0.6731`
  - sweep-dominant London sessions: next-session continuation `0.7233`

Interpretation:

- `USDJPY` carries directional state across session boundaries more cleanly than `EURUSD` and `GBPUSD`
- the pair split seen in R2 through R5 still holds after moving to multi-session sequences

## 6. Research Implications

Main lessons from R6:

- session-state sequences are more informative than isolated session summaries
- expanded London states are the most promising base condition for later New York continuation studies
- sweep events matter more once embedded in a session-state sequence than they did in isolation
- `USDJPY` should continue to be treated as a separate structural family, not pooled with the European pairs

What this suggests for later hypothesis generation:

- continuation studies should start with `expanded London -> New York` chains
- compression -> expansion transitions deserve attention, but only in the context of what the current session actually became
- London sweep sessions should not be discarded; in `USDJPY` and even `GBPUSD`, they can carry into New York as well as or better than breakout-dominant sessions
- later edge-candidate work should be sequence-based, not single-label based

## 7. Limitations

- this phase is still descriptive only
- no formal significance or multiple-testing layer has been applied yet
- pattern sparsity remains a real constraint, especially for pair-specific combinations
- only `EURUSD`, `GBPUSD`, and `USDJPY` were included
