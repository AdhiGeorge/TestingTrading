# XAUUSD Baseline Playbook — Research Status

## Important status

This document describes the untouched baseline rule set and the observed research results. **No final strategy was approved for live use.** The baseline and all 49 staged-search trials failed at least one required gate, primarily the minimum trade-count requirement and/or validation expectancy. The lock-out set was deliberately not opened.

The results are research evidence, not investment advice. M5 bars cannot reveal the order of events inside a candle, spreads widen around news and liquidity transitions, and historical results do not guarantee future performance.

## Rules tested

The baseline operates on XAUUSD M5 bid candles. Higher-timeframe candles are aligned to the 17:00 New York forex-day open, and a higher-timeframe candle is usable only after its close.

For a sell, the H4 structure must show two confirmed lower swing highs and two confirmed lower swing lows using a two-candle fractal width. The most recent confirmed swing high starts the leg. The first later bearish H4 candle supplies the key level at its open. An H1 candle must trade above that level and close back below it to validate the sweep. The first subsequent bearish M30 fair-value-gap or order-block POI is used; the entry is its midpoint. The order is placed only after the POI candle closes.

Buys are the mirror: higher highs and higher lows, a confirmed swing low, the first later bullish candle, an H1 sell-side sweep below the level that closes back above it, and a bullish M30 POI.

Orders are cancelled after 48 M5 bars, on invalidating closes, and at the weekend cutoff. One pending order or open trade is allowed at a time. If a bar touches both stop and target, the stop wins. A limit fill cannot also take profit on the same bar; the earliest target is the following bar.

## Scaled risk and cost rules

The primary run uses price-scaled spread: `0.0075% × current price per ounce`, with 0.5×, 1.0×, 1.5× and 2.0× stress cases. Stop buffer is `0.15 × ATR(14)` on H1. Stops smaller than `0.50 × ATR(14)` or larger than `5.0 × ATR(14)` are skipped. A first-bar gap larger than `1.0 × ATR(14)` on M5 blocks entry. Risk is 1% of current equity per trade, with 3R target in the untouched baseline.

The original fixed-dollar settings remain available as a secondary sensitivity case, but are not the primary conclusion because gold’s price scale changes materially across the sample.

## Results

The audited baseline generated 126 trades: 61 buys and 65 sells. Combined win rate was 28.6% at 3R, combined expectancy was 0.143R/trade, buy expectancy was −0.148R, and sell expectancy was +0.415R. The baseline did not meet the minimum 150-trade train / 60-trade validation gate.

Flat bars were retained. There were 198,773 flat M5 bars, 19.27% of the dataset. Approximately 57% of flat bars occurred in the defined New York 17:00–06:00 lower-liquidity window. This concentration is expected from the source feed and is a reason not to interpret the apparent edge as independent high-liquidity execution evidence.

## India time windows

All strategy logic is defined in New York time. For an India-based trader, the reference windows are:

| Window | US summer IST | US winter IST |
|---|---:|---:|
| London killzone | 11:30–14:30 | 12:30–15:30 |
| New York AM killzone | 16:30–19:30 | 17:30–20:30 |
| US equity open | 19:00 | 20:00 |
| London close | 19:30–21:30 | 20:30–22:30 |
| New York PM killzone | 23:00–01:30 | 00:00–02:30 |

These are display conversions only; implementation uses timezone-aware New York timestamps.

## What did not pass

No variant passed the full acceptance gates. The search logged 16 ablation, 3 greedy, and 30 interaction trials. High-expectancy/high-win-rate observations occurred only in small samples and failed the minimum-count gate; they were not promoted to a final strategy. No lock-out result is claimed.

## Live checklist if using this only as a paper-trading hypothesis

1. Confirm the feed is XAUUSD bid data and spread is currently normal.
2. Confirm H4 structure and wait for the relevant swing confirmation.
3. Mark the level and wait for the H1 sweep close; do not anticipate it.
4. Require a closed M30 POI after validation.
5. Calculate ATR-scaled stop eligibility and price-scaled spread before placing the limit.
6. Place the midpoint limit only after the POI closes; cancel after 48 M5 bars or invalidation.
7. Record New York and IST timestamps, direction, risk, stop, target, and reason.
8. Stop paper testing if live behavior departs materially from the assumptions: spread expansion, missing bars, execution gaps, or repeated overlap conditions.
