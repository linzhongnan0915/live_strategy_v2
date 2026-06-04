# BlackRock-Inspired Factor-to-Assets Notes (Prototype)

This memo summarizes how multi-factor thinking maps to ETF implementation in this workstation. It is original project documentation inspired by BlackRock and Andrew Ang style factor investing frameworks. It is **not** a reproduction of proprietary BlackRock materials.

## Factor, Not Only Asset Allocation

Portfolio risk is driven by **factor exposures** (growth, rates, inflation, credit, volatility, USD, EM risk), not only by asset labels. Two portfolios can hold different tickers but share the same factor risk if they load on the same macro drivers.

## What Factors Do We Own?

The prototype maps holdings and ETF sleeves to observable macro and style factors:

- Economic growth and equity beta (SPY, QQQ, IWM, sectors)
- Real rates and duration (SHY, IEF, TLT, TIP)
- Inflation and commodities (TIP, GLD, USO, XLE, DBA)
- Credit risk premium (LQD, HYG, EMB)
- USD and liquidity stress (UUP, front-end Treasuries)
- EM risk (EEM, VWO)
- Volatility monitor (VIX; not investable)

## What Factors Do We Want?

Strategy definitions in `strategy_library.csv` state target factor tilts (primary and secondary factors) and the ETF set used to express them. Ranking compares **desired factor expression** against **current market behavior** using prototype scores, not validated long-horizon backtests.

## How ETFs Implement Factor Exposure

ETFs are **implementation vehicles**:

- Broad beta sleeves implement growth and equity risk (SPY, VTI)
- Sector ETFs implement granular growth, cyclical, and defensive tilts
- Smart-beta ETFs implement quality, value, momentum, and minimum volatility
- Rates and credit ETFs implement duration and spread factors
- Real-asset ETFs implement inflation and geopolitical hedges

Factor exposure is never perfect: tracking error, sector composition, and liquidity constraints create **factor mismatch**.

## Why Constraints Matter

Real portfolios face constraints that pure factor models ignore:

- Long-only implementation in this prototype
- Liquidity tiers and minimum trade practicality
- Expense ratios and turnover budgets
- Minimum trade size and operational simplicity
- Tracking error versus ideal factor portfolio
- Calendar mismatches across ETFs, vol indexes, and commodities

## How This Project Applies the Idea

1. `etf_universe.csv` defines investable and monitor ETFs with factor tags.
2. `strategy_library.csv` defines 20 ETF sleeves with factor objectives and governance.
3. `strategy_ranker.py` produces a **prototype** ranking from price proxies and rule context.
4. `strategy_backtester.py` adds baseline sleeve backtests and WFO-style rolling OOS evaluation.
5. `news_monitor.py` translates breaking headlines into severity, topics, and strategy review candidates.
6. Dashboard windows separate **official EOD risk** (aligned OpenBB) from **live monitor-only** market/news layers.

## Current Limitations

- Walk-forward evaluation is prototype rolling OOS, not production alpha validation
- Ranking uses short-horizon return proxies, not Sharpe-optimal allocation
- Regime fit uses rule-engine alert linkage, not a full macro state model
- News severity is a risk-monitoring input, not an execution signal
- VIX is monitor-only; VXX is flagged as high-risk prototype only
- OpenBB/yfinance data is internship-grade, not Bloomberg institutional quality
