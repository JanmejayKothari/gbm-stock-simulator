# Mock Stock Contest Simulator

This project implements a mock stock contest backend that can:

- parse email-style trade orders,
- process crisis/news sentiment signals,
- simulate stock prices with geometric Brownian motion,
- execute validated trades for contest users,
- manage cash, holdings, realized/unrealized P&L, and
- produce a leaderboard.

The simulator core is intentionally independent of email and LLM services. Email/LLM integrations are adapters around the deterministic contest engine, which makes the system easier to test and safer to run.

## Quick Start

```bash
python demo.py
```

Run tests:

```bash
python -m unittest discover -s tests
```

## Email Flow

Incoming emails should be classified as either:

- `TRADE_ORDER`: buy/sell instructions
- `MARKET_SIGNAL`: crisis/news reports that affect drift/volatility
- `STOP`: stop the contest loop
- `OTHER`: ignored

Trades are parsed and validated before the portfolio state changes. Market-signal emails update sentiment scores, which affect the GBM price engine.

## Custom Stocks and Typo Handling

Add stocks in `demo.py` or the notebook setup cell with `StockConfig`:

```python
StockConfig("XYZ", "Example Industries", initial_price=25.0, shares_outstanding=100_000)
```

Then add aliases so email orders can use company names instead of only tickers:

```python
parser = EmailOrderParser(
    aliases={
        "example industries": "XYZ",
    }
)
```

The parser uses conservative fuzzy matching for stock names. Obvious typos such as `Exmaple Industries` can resolve to `XYZ`, but weak or ambiguous names are rejected before execution. This avoids accidental trades in the wrong company.

## Security

Do not hard-code Gmail passwords or OpenAI API keys in notebooks or source code. Pass credentials through environment variables or a separate secrets manager.
