
XAUUSD Strategy Backtest Spec
Nov 2, 2026 · @Adithya. S. George
Give this document to Manus as the full build brief: it turns your liquidity-sweep strategy into testable rules, a staged search plan, and a final playbook you can trade from.
1. Brief for Manus
Goal. Build a Python backtesting and research framework on 10+ years of XAUUSD 5-minute MT5 data. Encode the core strategy in section 3 exactly, then refine each part (bias, level, sweep, point of interest, entry, stop, target, time filter) by testing the modules in section 4. Return the best robust rule set as a plain-English playbook.
Optimise expectancy, not raw win rate. With a fixed 1:3 reward-to-risk, break-even win rate is 25%. A tiny take-profit can show a 90% win rate and still lose money. Rank every variant by this order:
1.	Expectancy in R (average R per trade, after spread and slippage)
2.	Profit factor and maximum drawdown
3.	Stability across years, sessions and market regimes
4.	Win rate, always reported next to its RR, never alone
The user still wants the highest win rate possible. Report it as a column and as a secondary ranking, but only among variants that pass the gates in section 8.
Guard against overfitting. Testing thousands of combinations on one dataset will always find a "great" result by luck. Manus must therefore:
•	Split the data by time: train, validation and a final lock-out set that is touched only once (section 6).
•	Search in stages, not as one giant grid.
•	Require a minimum trade count (at least 150 trades in train, 60 in validation) before a variant is eligible.
•	Prefer plateaus over peaks: a setting is trusted only if its neighbours also work.
•	Run a permutation or shuffled-entry test on the final winner and report the result.
Rules for the code.
•	No look-ahead: a higher-timeframe candle, swing, or fair value gap is usable only after it has fully closed and been confirmed.
•	Every number that can vary is a parameter in one config file (YAML or JSON), never hard-coded.
•	Every trade is logged with the reason it was taken, so the user can audit it on a chart.
•	Reproducible: fixed random seeds, a pinned requirements file, one command to rerun everything.
2. Data and clock
The input is MT5 M5 bars for XAUUSD (time, open, high, low, close, tick volume, spread). Manus must validate the file before any test and print a data-quality report.
Checks to run
•	Duplicate or non-monotonic timestamps, missing weekday bars, and gaps longer than 30 minutes outside the weekend.
•	Bars where high < low, or open/close outside the high-low range.
•	Spread column: median and 99th percentile by year. If it is zero or missing, use a fixed spread parameter (default $0.30 per ounce, tested at $0.20, $0.30 and $0.50).
•	Total bars per year, to confirm the history really covers 10+ years of M5.
Timezone handling (critical)
MT5 timestamps are broker server time, not UTC. Most brokers use GMT+2 in winter and GMT+3 in summer, switching with US daylight saving so that the daily candle closes at 17:00 New York. Manus must:
1.	Detect the offset by checking that the weekly open and the Friday close line up with 17:00 New York, then store the rule as a function, not a constant.
2.	Convert every bar to UTC, then to two derived columns: ny_time (America/New_York) and ist_time (Asia/Kolkata, always UTC+05:30, no daylight saving).
3.	Define all session logic in New York time (the way ICT concepts are taught) and display results in IST. Section 7 gives the conversion table.
Higher timeframes
Build M15, M30, H1, H4, D1, W1 and MN bars by resampling M5, aligned to the 17:00 New York daily open. The weekly bar opens Sunday 17:00 New York. Mark each resampled bar with the timestamp at which it closes, and let strategy code read only bars whose close time is at or before the current M5 bar.
Other instruments
The first build uses XAUUSD only. Keep the code instrument-agnostic (tick size, contract size and spread live in config) so EURUSD, GBPUSD, USDJPY, USDCAD and Nasdaq can be tested later with the same frozen rules, as a pure out-of-sample check.
3. Core strategy as testable rules
This is the baseline, written for sells. Buys are the exact mirror (swap highs and lows, bearish and bullish, above and below). The baseline must be coded first and its results reported untouched, so every later refinement can be compared against it.
Step 1: Bias (H4)
•	A swing high is an H4 candle whose high is the highest of N candles on each side. A swing low is the mirror. Default N = 2, tested at 2, 3 and 5. A swing counts only after N later candles have closed.
•	Bearish bias: the last two confirmed swing highs are lower highs and the last two swing lows are lower lows. Bullish bias is the mirror. Anything else is a range and gives no trade in the baseline.
•	Bias flips when price closes beyond the last opposing swing (a break of structure). The close-versus-wick test is a parameter.
Step 2: Key level (sell)
Pick the most recent confirmed swing high. The key level is the open price of a bearish H4 candle in the leg that starts at that swing high. Which candle is a parameter:
Option	Candle used
K1	The first bearish candle after the swing high
K2	The bearish candle that contains the swing high
K3	The largest-body bearish candle in the first 3 candles of the drop
K4	Any bearish candle in the leg that is later tapped (test all, keep the best)
Step 3: Classify the level after every H4 close
Situation	What happened to the level	Validation needed
A	No later H4 candle has traded up to the level	H1 sweep (Step 4)
B	A later H4 candle wicked above the level and closed back below it	None: that H4 candle is the sweep. Validated at its close
C	A later H4 candle closed above the level	H1 sweep (Step 4) after the break
Step 4: H1 sweep (situations A and C)
Watch H1 candles. The first H1 candle whose high is above the level decides everything:
•	If it closes back below the level, the level is validated (liquidity swept, rejected). Record the sweep high and the validation time.
•	If it closes above the level, the level is dead and there is no trade on it. In situation C, price must come back below and a new H1 candle must sweep and close below.
Parameters: minimum wick beyond the level (0, 0.1 or 0.25 times ATR), and whether invalidation uses the H1 close (default) or the H4 close.
Step 5: Entry (M30, M15, M5)
After validation, scan M30, M15 and M5 for a point of interest (POI) that supply is likely to defend. The POI type is the main thing to refine (section 4). The baseline POI is the most recent bearish fair value gap or order block formed after the sweep. Place a sell limit at the POI price. The baseline entry is the POI midpoint.
Cancel the order if any of these happen first: price closes above the sweep high; N bars pass unfilled (default 48 M5 bars); the session window closes (if a time filter is on).
Step 6: Stop and target
•	Baseline stop: above the sweep high plus a buffer of $0.30 plus the spread.
•	Baseline target: 3R. Section 4 lists the dynamic targets to test.
•	Risk is 1% of equity per trade (section 5).
Counter-trend trades. The user can also take a buy inside a bearish structure "if the situation tells me to". Code this as a switch, off in the baseline, with the situations to test: an H4 market structure shift, a sweep of a major low into a discount zone, or a sweep of the previous weekly low.
4. Module library to test
Each row is a switchable module with exact coding rules, so Manus tests the same idea the same way every time. Your list of ICT and smart money concepts is covered; extra ones (ATR filters, round numbers, volatility regimes) are added where they help the core strategy. Every module is tested against the baseline in section 3, one layer at a time, before any combinations (section 6).
A. Bias and context
Module	How to code it	Options to test
Top-down start	Bias timeframe that must agree	Monthly, Weekly, Daily, H4 only; or agreement of 2 or 3 of them
Swing size	Fractal width N on the bias timeframe	2, 3, 5
Structure break	BOS or MSS: candle close beyond the last swing, with a displacement candle (body at least 1.5 times average body of the last 20)	Close vs wick; displacement on/off
Premium / Discount	Dealing range = last confirmed swing high to swing low. Above 50% is premium, below is discount	Sells only in premium, buys only in discount; thresholds 50%, 62%, 70%
Draw on liquidity	The nearest unswept pool in the bias direction is the target	PDH/PDL, PWH/PWL, session extremes, EQH/EQL
Regime filter	Trend strength and volatility	ADX above 20 or 25; ATR(14) on H4 in a low, mid or high bucket
B. Key level and liquidity
Module	How to code it	Options to test
Level candle choice	K1 to K4 from section 3	All four
Level type	What gets treated as the level	Candle open (baseline), order block body, order block wick, 50% of the candle
Relative equal highs/lows	Two or more swing highs within a tolerance	0.1, 0.2, 0.3 times ATR(14)
PDH/PDL, PWH/PWL	Previous day or week extreme, daily open at 17:00 New York	Sweep of these as a required or bonus condition
Session highs/lows	Asian, London, New York ranges in New York time	Which session's extreme was swept before entry
Sweep rule	Wick beyond the level and close back inside	Timeframe: M15, M30, H1 (baseline), H4. Minimum penetration 0, 0.1, 0.25 ATR
C. Confirmation after the sweep
Module	How to code it	Options to test
MSS / Smart Money Reversal	After the sweep, a lower-timeframe close below the last swing low, with displacement	M5, M15, M30; required vs not required
CISD	Close beyond the open of the run of same-colour candles that led into the sweep	M5, M15; body close vs wick
SMT divergence	XAUUSD makes a new extreme that a correlated instrument does not (needs extra data, section 8)	XAGUSD, DXY, EURUSD; optional
Market maker model	Accumulation, then manipulation (the sweep), then distribution. Detect as range, sweep, MSS in order	MMSM for sells, MMBM for buys; on/off as a filter
D. Point of interest (entry zone)
Module	How to code it	Options to test
Fair value gap (FVG)	Three-candle gap: for a sell, candle 1 low above candle 3 high. Zone = that gap	Timeframe M5, M15, M30; minimum size 0.1 to 0.5 ATR
First presented FVG	The first FVG that forms after the MSS or CISD	On vs any FVG
Evolving FVG	A gap that grows as new candles extend it during displacement; zone is the final merged gap	On/off
Inverted FVG (iFVG)	A bullish FVG that price closes through, which then acts as resistance for sells	Entry on the retest of the flipped gap
Order block (OB)	Last bullish candle before a bearish displacement that breaks structure	Body only vs full range; mean threshold (50%)
Breaker block	An order block that failed (price swept it and then broke structure the other way), retested from the other side	On/off
Rejection block	The long wick portion of a candle at the sweep	Wick zone vs wick midpoint
OTE	Fib retracement of the displacement leg after the MSS	0.62, 0.705, 0.79; zone entry or single level
Overlap	Two or more of the above overlapping	Count of overlapping zones required: 1, 2, 3
Simple support/resistance	Prior swing levels and round numbers ($X00 and $X50)	As confluence only
E. Entry price
Options per POI: zone edge nearest price (aggressive), zone midpoint (baseline), zone far edge (conservative), or a market entry on the candle close that confirms. Also test limit fills with and without a one-tick penetration requirement.
F. Stop loss
Option	Placement
S1	Above the sweep high, buffer $0.30
S2	Above the POI zone, buffer $0.30
S3	Entry plus 1.0, 1.5 or 2.0 times ATR(14) on the entry timeframe
S4	Above the last swing high on the entry timeframe
Skip any trade whose stop is smaller than $1.50 or larger than a cap (test $15, $25, $40), because the spread dominates tiny stops.
G. Take profit and management
Option	Rule
T1	Fixed RR: 1, 1.5, 2, 3, 4
T2	Next liquidity pool in the trade direction: previous day or week low, session low, EQL, last swing low; take the trade only if it gives at least 2R
T3	Standard deviation projection of the sweep-to-MSS leg: minus 1, minus 2, minus 2.5, minus 4
T4	Partials: close 50% at 1R and move stop to break-even, rest to T1/T2/T3
T5	Dynamic RR: RR set by the distance to the nearest draw on liquidity, capped between 1.5 and 5
Time stop	Close at market after N bars (24, 48, 96 M5 bars) or at the end of the session
H. Time filters (all defined in New York time, shown in IST in section 7)
Killzones, macro windows (the 10 minutes before and after the hour or half hour), Silver Bullet windows, day of week, and a high-impact news blackout (30 minutes either side of scheduled releases, only if a calendar file is supplied).
5. Execution simulation rules
These rules make the backtest conservative. When a rule is unclear, Manus must choose the assumption that makes results worse, not better.
Prices. MT5 M5 bars are bid prices. A sell enters and exits at bid for entries and at ask (bid plus spread) for stops and targets; a buy is the reverse.
Event	Sell trade rule	Buy trade rule
Limit fill	Bar high (bid) reaches the limit price	Bar low plus spread reaches the limit price
Stop hit	Bar high plus spread reaches the stop	Bar low reaches the stop
Target hit	Bar low plus spread reaches the target	Bar high reaches the target
Stop gap or slippage	Fill at the worse of stop price and bar open, plus 0.5 times the spread	Same, mirrored
Same-bar conflicts
•	If a bar touches both stop and target, the stop is assumed to hit first.
•	If a limit order fills on a bar that also reaches the stop, the trade is a full loss.
•	If a limit order fills and the same bar reaches the target but not the stop, count the target as hit only on the next bar. This removes the optimistic fill-and-run bias of 5-minute data.
Order handling
•	A POI is known only after the bar that completes it has closed. The limit order is placed at the next bar's open.
•	One open trade or pending order at a time in the baseline. Test a variant that allows two.
•	Orders do not carry over the weekend. Close or cancel everything 10 minutes before the Friday close (17:00 New York).
•	Do not trade on the first M5 bar after a gap larger than $5.
Position sizing
•	Risk 1% of current equity per trade, compounded. Also report fixed-dollar risk (1% of starting equity) so equity curves are not dominated by late compounding.
•	Lot size = risk amount divided by (stop distance in dollars times 100 ounces per lot), rounded down to 0.01 lot. Contract size and minimum lot live in config.
•	Skip the trade if the rounded lot gives more than 1.2% risk or the stop distance gives less than 0.01 lot.
•	Starting equity default: $10,000, shown in both USD and INR (convert at a fixed rate in config, for readability only).
Costs. Spread from the data (or the fixed fallback), plus a commission parameter (default $0, tested at $7 per round-turn lot). Swap is ignored for intraday holds and applied at a fixed rate for trades held past 17:00 New York.
Audit trail. Every trade row stores: level candle time, situation (A/B/C), sweep time and high, POI type and timeframe, entry, stop, target, fill time, exit time and reason, R result, and the IST and New York time of entry. A chart image is saved for a random sample of 30 trades so the user can check the logic visually.
6. Search plan
Testing every combination at once is impossible (the modules above multiply into billions of variants) and would find luck, not edge. Manus runs six stages, and each stage keeps only what survives.
Data splits (by time, never shuffled)
Set	Share of history	Use
Train	Oldest 60% (roughly the first 8 years)	Build and rank variants
Validation	Next 20% (roughly 2.5 years)	Choose between finalists
Lock-out	Newest 20% (roughly 2.5 years)	Opened once, for the single final candidate
Also run a rolling walk-forward on the train and validation years: optimise on 4 years, test on the next 1 year, roll forward by 1 year, and join the test years into one out-of-sample equity curve.
Stages
1.	Baseline. Run section 3 untouched. Report every metric in section 8, by year.
2.	Layer ablation. Change one layer at a time (bias start, level candle, sweep rule, POI type, entry price, stop, target, time filter) and compare with the baseline. This answers "what matters" cheaply, in a few hundred runs.
3.	Greedy build. For each layer, keep the top 2 or 3 options, then add layers one by one. Keep an addition only if validation expectancy improves, the trade count stays above the minimum, and neighbouring parameter values do not collapse.
4.	Interaction search. Run a capped search (Optuna or a random search, at most 20,000 trials) over the survivors of stage 3, to find combinations that work together (for example sweep rule with POI type with stop type). Log the total number of trials; it is needed for the statistics in stage 6.
5.	Stress tests on the top 10 variants. Spread times 1.5 and times 2; entry delayed by one bar; stop widened by 10%; each year and each session removed in turn; Monte Carlo reshuffle of trade order (1,000 runs) for the 95th percentile drawdown; results by market regime (trend vs range, high vs low volatility).
6.	Significance and lock-out. Apply a multiple-testing correction (deflated Sharpe ratio or White's reality check) using the trial count from stage 4, and a permutation test that randomises entry times inside the same sessions. Only a variant that passes goes to the lock-out set, once. If it fails there, report that honestly and give the validation result as the best estimate.
How to keep the search fast
Split the work into two cached steps. First, compute all validated sweep events once for each bias, level and sweep setting (these depend only on higher timeframes). Second, for each event, run the entry, stop and target modules on the lower timeframes. Use numpy or numba, and save intermediate tables to Parquet so a changed target rule does not recompute the sweeps.
7. IST adaptation
Sessions are defined in New York time because that is how the concepts are taught, then converted to IST (UTC+05:30, no daylight saving). New York is 9h30 behind IST while US daylight saving applies (March to early November) and 10h30 behind IST otherwise. US daylight saving ended on 1 November 2026, so the winter column applies now, until mid-March 2027. Manus must do this conversion with timezone-aware code, never with a fixed offset.
Window	New York time	IST in US summer time	IST in US winter time
Forex day open (daily candle)	17:00	02:30	03:30
Asian killzone	20:00 to 00:00	05:30 to 09:30	06:30 to 10:30
Midnight open	00:00	09:30	10:30
London killzone	02:00 to 05:00	11:30 to 14:30	12:30 to 15:30
New York AM killzone	07:00 to 10:00	16:30 to 19:30	17:30 to 20:30
US data releases (8:30 news)	08:30	18:00	19:00
US equity open	09:30	19:00	20:00
London close killzone	10:00 to 12:00	19:30 to 21:30	20:30 to 22:30
New York PM killzone	13:30 to 16:00	23:00 to 01:30	00:00 to 02:30
Silver Bullet, London	03:00 to 04:00	12:30 to 13:30	13:30 to 14:30
Silver Bullet, New York AM	10:00 to 11:00	19:30 to 20:30	20:30 to 21:30
Silver Bullet, New York PM	14:00 to 15:00	23:30 to 00:30	00:30 to 01:30
These windows are the starting definitions. Manus should also test shifting each by up to 30 minutes, since the best gold windows are not always the textbook ones.
What Manus must add for an India-based trader
•	Personal trading window. A config setting ist_trade_hours (for example 17:00 to 23:30 IST) that blocks trades outside the hours the user can actually watch the chart. Run the whole search once with no restriction and once with the user's window, and show the cost of the restriction.
•	Results by IST hour and IST weekday. Win rate, expectancy and trade count for each IST hour, so the user sees when the strategy works for them. Trades that cross midnight IST are grouped by their entry time in IST.
•	Pending-order friendly. Because the entry is a limit order, report how many trades would have been placed at least 30 minutes ahead of the fill, so the user can set the order and step away.
•	Display. Every time in reports, charts and trade logs shows IST first and New York in brackets. Account values show USD with an INR figure beside it.
8. Metrics, gates and deliverables
Metrics for every variant: trades, win rate, average win and loss in R, expectancy in R, profit factor, total return, maximum drawdown, longest losing streak, Sharpe and Sortino ratio on daily returns, average holding time, and results by year, quarter, session, IST hour and weekday.
Gates. A variant enters the final leaderboards only if it passes all of these on validation (and later on lock-out):
Gate	Threshold
Trade count	At least 150 in train, 60 in validation
Expectancy after costs	At least +0.20R per trade
Profit factor	At least 1.3
Maximum drawdown at 1% risk	At most 20% (Monte Carlo 95th percentile at most 25%)
Profitable years	At least 70% of years positive
Cost stress	Still positive with spread times 1.5
Neighbour test	Settings next to the chosen ones stay positive
Significance	Passes the stage 6 correction and permutation test
Two leaderboards. Leaderboard 1 ranks by expectancy in R. Leaderboard 2 ranks by win rate, among variants that pass all gates, and shows the RR used. The user wants the highest win rate possible; the gates stop that ranking from rewarding strategies that win often and lose money.
Deliverables Manus must return
1.	The code repository with a README, a config file, a requirements file and one command to reproduce every table.
2.	The data-quality report from section 2.
3.	Results tables (CSV) for every stage, plus both leaderboards.
4.	A full trade log (CSV) for the final strategy, with the audit fields from section 5, and 30 sample trade charts.
5.	Equity curve, drawdown curve and monthly return heatmap for train, validation, lock-out and walk-forward.
6.	The Playbook (a separate document, written for a trader, not a programmer). It must contain: the final rules in plain steps for sells and buys; a one-page checklist to use live; the exact stop, target and risk rules; the best IST trading windows with the winter and summer conversions; the 3 to 5 annotated example trades; the statistics with confidence ranges; the conditions in which the strategy stops working; and a list of what did not work, so the user does not retest it.
7.	A short honest note on limits: M5 data cannot show the order of events inside a bar, spread widens at news, and past results do not guarantee future results.
Optional extra data (improves the SMT and news tests)
M5 files for XAGUSD and DXY (or EURUSD), a CSV economic calendar with impact levels, and M5 history for GBPUSD, USDJPY, USDCAD, EURUSD and Nasdaq. If these are not supplied, Manus skips those modules and says so in the report. Never invent data.
Message to paste into Manus together with this document
"Read the attached specification fully. Build the framework in the order given, report the untouched baseline first, follow the staged search and the no-look-ahead rules, and treat the lock-out set as single-use. Do not stop at a high win rate: rank by the gates in section 8. Ask me only if the data file is missing or unreadable. Return the deliverables in section 8."
