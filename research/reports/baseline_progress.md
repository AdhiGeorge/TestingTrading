# Engine and untouched baseline progress

## Scaling used

The primary run replaces fixed-dollar thresholds with ATR/price-scaled rules:

- spread: `0.0075% * price * multiplier` per ounce; primary multiplier 1.0; stress multipliers 0.5, 1.5, and 2.0;
- stop buffer: `0.15 * ATR(14)` on H1;
- minimum stop: `0.50 * ATR(14)` on H1;
- stop cap: `5.0 * ATR(14)` on H1;
- gap filter: `1.0 * ATR(14)` on the M5 bar.

The original dollar values remain configured for a secondary sensitivity run.

## Baseline

The untouched baseline engine produced **130 trades**: 63 buys and 67 sells. Combined expectancy is **0.138R/trade**, with 28.5% win rate at 3R target. Sell expectancy is **0.373R** and buy expectancy is **−0.111R**. No implausible >80% win rate or >1R combined expectancy was observed.

The baseline fails the minimum-trade gate (150 train trades and 60 validation trades), so it is not a final candidate. It also has too few trades in individual years for stable annual inference.

## Flat bars

Flat bars are retained. Total flat bars: **198,773 (19.27%)**. The detailed yearly count/share and concentration diagnostic is in `data_quality_flat_bars.json`. The low-liquidity concentration field measures the share of flat bars occurring in New York 17:00–06:00.

## Directional result

The full year-by-year long/short/combined table is `baseline_metrics.csv`; it reports expectancy, win rate, average win/loss, profit factor, trade count, total R, and holding time.

## Caveat

This is an engine-stage baseline, not a selected strategy. The staged search will apply train/validation gates, stress tests, walk-forward evaluation, permutation testing, and a single lock-out evaluation.
