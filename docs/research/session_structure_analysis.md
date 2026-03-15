# Session Structure Analysis

## 1. Scope

Pairs analyzed:

- `EURUSD`
- `GBPUSD`
- `USDJPY`

Timeframe:

- `15m`

Sample period:

- `2018-01-01 22:00:00+00:00` through `2024-12-31 21:45:00+00:00`

Timestamp and session conventions:

- UTC bar-open timestamps
- FX trading date anchored to the repo’s existing `22:00 UTC` rollover
- `fx_session_date = (timestamp + 2h).date`, so bars from `22:00-23:45 UTC` start the next FX trading date

Session definitions reused from the existing repo:

- `asia`: `00:00-07:00 UTC`
- `london`: `07:00-13:00 UTC`
- `new_york`: `13:00-24:00 UTC`

Outputs:

- `outputs/diagnostics/session_structure/session_summary_by_pair.csv`
- `outputs/diagnostics/session_structure/pooled_cross_pair_session_summary.csv`
- `outputs/diagnostics/session_structure/session_return_distribution.csv`
- `outputs/diagnostics/session_structure/normalized_behavior_by_regime.csv`
- `outputs/diagnostics/session_structure/session_transition_summary.csv`
- `outputs/diagnostics/session_structure/summary_notes.json`

## 2. Raw Session Behavior

Headline pair/session differences:

- `EURUSD` is slightly negative on average in all three sessions:
  - Asia `-0.000044`
  - London `-0.000102`
  - New York `-0.000058`
- `GBPUSD` is also slightly negative, but its session ranges are larger than `EURUSD` in every session:
  - Asia range `0.002874` vs `0.002416`
  - London range `0.005216` vs `0.004113`
  - New York range `0.006692` vs `0.005297`
- `USDJPY` is structurally different in this sample:
  - positive average return in Asia `0.000058`
  - positive average return in London `0.000079`
  - strongest positive average return in New York `0.000236`

Cross-pair session structure:

- London and New York are materially larger-range sessions than Asia across all three pairs.
- New York is the highest-range session for every pair.
- Session continuation from the first bar is mildly above 50% in most raw summaries, but not dramatically so:
  - Asia pooled continuation `0.5816`
  - London pooled continuation `0.5649`
  - New York pooled continuation `0.5200`

Raw directional structure:

- directional efficiency rises from Asia into later sessions:
  - pooled Asia `0.1912`
  - pooled London `0.2169`
  - pooled New York `0.2350`
- `USDJPY` closes are persistently skewed toward the top of the session range:
  - Asia CLV `0.5398`
  - London CLV `0.5413`
  - New York CLV `0.5506`
- `EURUSD` is the weakest on close placement, especially in London:
  - London CLV `0.4794`

Interpretation:

- `USDJPY` behaves structurally differently from the two European pairs in this sample, with a persistent positive-close bias across sessions.
- `GBPUSD` is the broadest-range pair, but not the strongest on average directional return.
- the raw pair tables alone do not reveal much about when continuation or reversal is more likely; that only becomes clearer after normalization.

## 3. Normalized State Behavior

This was the main purpose of the phase: not just `pair -> statistic`, but `normalized state -> statistic`.

### Volatility regime

Within each pair and session, realized session volatility was bucketed into `low`, `medium`, and `high` quantile buckets.

Pooled effects:

- high-volatility Asia is wider but not directionally stronger:
  - avg range `0.004729`
  - continuation `0.5861`
  - avg return `-0.000087`
- high-volatility London turns clearly more negative than low-volatility London:
  - high-vol avg return `-0.000181`
  - low-vol avg return `0.000044`
- the same effect appears in New York:
  - high-vol avg return `-0.000240`
  - low-vol avg return `0.000229`

What only becomes visible after normalization:

- raw London and New York means look close to flat pooled, but the regime split shows a cleaner pattern:
  - higher volatility creates larger range and somewhat more directional path behavior
  - but average signed return deteriorates rather than improves
- that is a useful caution for later hypothesis work: “more motion” is not the same as “better directional carry.”

### Range compression / expansion regime

Range regime was defined using current session range relative to the trailing 20-session median range for the same pair and session:

- `< 0.8`: `compressed`
- `0.8-1.2`: `normal`
- `> 1.2`: `expanded`

Pooled effects:

- compressed regimes have the highest continuation probabilities:
  - Asia `0.6070`
  - London `0.5904`
  - New York `0.5688`
- expanded regimes are much more directional by efficiency ratio:
  - Asia efficiency `0.2805`
  - London efficiency `0.3147`
  - New York efficiency `0.3117`
- but expanded London and New York also have the weakest signed returns:
  - London expanded avg return `-0.000203`
  - New York expanded avg return `-0.000179`

What only becomes visible after normalization:

- raw session summaries make London and New York look like the most directional sessions.
- the range-regime split shows that this directionality is concentrated in expanded states, while those same states also carry the weakest signed mean return.
- compressed sessions are less directional by path, but more stable on continuation probability.

### Time-since-extreme regime

Extreme regime was defined from bars since the last `15m` bar whose body was at least `1.5 * ATR(14)`:

- `<= 8` bars: `recent_extreme`
- `9-32` bars: `intermediate`
- `> 32` bars: `stale`

Pooled effects:

- Asia after a recent extreme becomes more continuation-heavy:
  - continuation `0.6340`
  - avg return `-0.000064`
  - range `0.003558`
- New York after a recent extreme shows the clearest positive skew:
  - avg return `0.000167`
  - continuation `0.5434`
  - CLV `0.5329`
- stale London sessions are the weakest of the London buckets:
  - avg return `-0.000130`
  - continuation `0.5210`

What only becomes visible after normalization:

- the raw tables do not show that Asia becomes much more one-directional after a recent extreme.
- they also do not show that New York has a more favorable positive-close profile after recent extremes than in stale states.

## 4. Directional Efficiency And CLV

Directional Efficiency Ratio:

- pooled by session:
  - Asia `0.1912`
  - London `0.2169`
  - New York `0.2350`
- by range regime, efficiency rises sharply in expanded states:
  - London compressed `0.1334` vs expanded `0.3147`
  - New York compressed `0.1957` vs expanded `0.3117`

Interpretation:

- expanded sessions are materially more directional in path terms
- compressed sessions are much choppier

Close Location Value:

- pooled CLV is close to neutral overall, but pair dispersion matters
- `USDJPY` is persistently top-heavy:
  - all sessions above `0.539`
- `EURUSD` is the weakest:
  - London `0.4794`
  - New York `0.4942`

Volatility-conditioned CLV:

- pooled high-vol London CLV drops to `0.4947`
- pooled low-vol London CLV rises to `0.5131`
- pooled low-vol New York CLV is also stronger at `0.5269`

Interpretation:

- later-session directional structure exists, but the close location skew is pair-specific
- `USDJPY` has a persistent upward close bias that is not present in the European pairs

## 5. Session Transition Findings

### Asia -> London

Unconditional pooled transition behavior is nearly balanced:

- after negative Asia: continuation `0.4987`, reversal `0.5009`
- after positive Asia: continuation `0.5011`, reversal `0.4985`

Interpretation:

- there is no strong unconditional Asia-to-London carry effect in these three pairs
- this transition should not be treated as a generic continuation or reversal regime without further context

### London -> New York

This transition is materially different:

- after negative London: continuation `0.6899`, reversal `0.3097`
- after positive London: continuation `0.7110`, reversal `0.2883`

Conditional on prior London volatility:

- high-vol prior London strengthens continuation further:
  - negative London -> NY continuation `0.7304`
  - positive London -> NY continuation `0.7365`
- low-vol prior London is weaker:
  - negative London -> NY continuation `0.6321`
  - positive London -> NY continuation `0.6823`

Interpretation:

- the strongest descriptive transition effect in this phase is London-to-New York continuation
- that continuation is more pronounced when the prior London session itself was high-volatility

## 6. Research Implications

This phase is descriptive only, but it narrows the space of future hypotheses.

Promising structural directions:

- London-to-New York continuation deserves further descriptive follow-up because it is the clearest transition asymmetry in the current outputs.
- Range regime matters:
  - expanded sessions are much more directional in path terms
  - compressed sessions show higher continuation probability despite lower efficiency
- recent-extreme state matters:
  - Asia after a recent extreme behaves differently from stale Asia
  - New York after a recent extreme closes stronger and higher in-range than stale New York
- `USDJPY` is structurally different enough that future cross-pair research should not assume `EURUSD` and `GBPUSD` behavior transfers to it directly

Non-conclusions that should be avoided:

- high volatility is not automatically favorable for directional ideas
- large session range is not automatically favorable for positive signed returns
- raw pair/session averages are too coarse on their own to define a useful hypothesis set

## 7. Limitations

- only `EURUSD`, `GBPUSD`, and `USDJPY` were included
- this is descriptive analysis only, not a significance-testing phase
- no tradability claim follows directly from these tables
- regime buckets are intentionally coarse and meant for structural comparison, not optimization
- `low_sample` rows are flagged in the machine-readable outputs and should not drive conclusions
