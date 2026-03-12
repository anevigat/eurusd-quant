# VWAP Band Reversion (Filtered) — Research Mapping

## Status

Verdict: `already_researched`

## Why this is marked already researched

This concept is already covered by the existing VWAP intraday reversion research stream:

- `docs/strategy_vwap_intraday_reversion.md`
- `outputs/vwap_intraday_reversion_diagnostic/`
- `outputs/vwap_intraday_reversion_smoke/`

That work already evaluated:

- intraday VWAP proxy behavior on EURUSD M15
- deviation regimes (small / medium / large / extreme)
- session-scoped analysis (`07:00-17:00 UTC`)
- short reversion horizons (`4-8` bars)
- filtered MVP entry threshold (`deviation_threshold_atr = 2.8`)

## Conclusion

The requested filtered VWAP-band concept materially overlaps the completed VWAP intraday reversion diagnostic and MVP research, so no duplicate diagnostic was rerun in this batch process.
