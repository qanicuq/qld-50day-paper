# QLD 50-day paper bot

Paper money only. No real orders are ever placed.

**Rule:** after each market close, if QLD closed above its 50-day average, hold QLD starting at the next day's open. If it closed below, sell and sit in cash starting at the next day's open.

- Starts with $10,000 of paper money.
- Runs once every weekday after the close (GitHub Actions).
- Sends a push alert on every buy signal, sell signal and fill, and if a run fails.

**Files:**
- `state.json`: what the paper account holds right now
- `trades.csv`: every paper buy and sell
- `equity.csv`: the account value at each day's close

**Backtest (Jul 2021 to Oct 2026, 30-minute QLD data):** +168% vs +128% for holding QLD, with a worst drop of −31% vs −65%. It lagged holding QLD in strong up years and did best in falling years such as 2022.

Prices come from Yahoo Finance daily bars, which are split-adjusted.
