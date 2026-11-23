# Mock Stock Contest Simulator

This project is a lightweight backend engine for running a mock stock-trading contest. It was designed for a game-like setting where participants submit trades, hold simulated portfolios, react to news or crisis events, and compete on a leaderboard.

Unlike a real trading system, this project does not connect to live markets or execute real orders. Stock prices are generated inside the simulator using geometric Brownian motion, with optional sentiment/news signals that can nudge drift and volatility.

## What It Does

The simulator can:

- parse email-style trade orders,
- process crisis/news sentiment signals,
- simulate stock prices with geometric Brownian motion,
- execute validated trades for contest users,
- manage cash, holdings, realized/unrealized P&L, and
- produce a leaderboard.

The simulator core is intentionally independent of Gmail, OpenAI, or any specific external service. Email and LLM integrations should act as adapters around the deterministic contest engine. That makes the project easier to test, safer to run, and simpler to customize for different contest formats.

## Project Structure

```text
.
├── simulator_engine.py              # Main simulator engine
├── demo.py                         # Runnable example flow
├── contest_demo.ipynb   # Notebook wrapper/demo
├── tests/
│   └── test_simulator_engine.py     # Unit tests
├── README.md
└── .gitignore
```

The most important file is `simulator_engine.py`. It contains the pricing engine, order parser, portfolio manager, trade execution logic, and leaderboard generation.

## Quick Start

```bash
python demo.py
```

Run tests:

```bash
python -m unittest discover -s tests
```

## How The Contest Works

At a high level, the contest loop is:

```text
Email-style message
  -> classify as trade, market signal, stop, or ignore
  -> parse into a structured order or signal
  -> validate user, password, ticker, quantity, cash, and holdings
  -> execute valid trades at the current simulated price
  -> advance prices with GBM
  -> mark portfolios to market
  -> update leaderboard
```

Trades never mutate portfolios directly from raw text. The text is parsed into a `TradeOrder`, then validated by the simulator before any cash or holdings change.

## Email Flow

Incoming emails should be classified as either:

- `TRADE_ORDER`: buy/sell instructions
- `MARKET_SIGNAL`: crisis/news reports that affect drift/volatility
- `STOP`: stop the contest loop
- `OTHER`: ignored

Trades are parsed and validated before the portfolio state changes. Market-signal emails update sentiment scores, which affect the GBM price engine.

Example structured trade:

```text
stock: AAA
quantity: 100
portfolio: team_1
password: pass001
buy/sell: +1
```

Example sentence-style trade:

```text
Portfolio team_1 password pass001 wants to buy 100 shares of Alpha Corp.
```

## Pricing Model

Prices are simulated with geometric Brownian motion:

```text
S_next = S_current * exp((mu - 0.5 * sigma^2) * dt + sigma * sqrt(dt) * Z)
```

Where:

- `mu` is the annual drift,
- `sigma` is the annual volatility,
- `dt` is the time step,
- `Z` is a random normal shock.

Market-signal events can adjust a stock's effective drift and volatility. For example, a positive crisis/news signal can increase sentiment-adjusted drift, while a high-uncertainty signal can increase volatility.

## Portfolio Management

Each contest user has:

- a user/portfolio ID,
- a password,
- a cash balance,
- stock holdings,
- average cost basis,
- realized P&L,
- unrealized P&L,
- trade history.

The leaderboard ranks users by total portfolio value:

```text
cash + current market value of holdings
```

Invalid trades are rejected. For example:

- unknown portfolio,
- bad password,
- unknown stock,
- insufficient cash,
- insufficient shares,
- invalid quantity.

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

Add contest users with `UserConfig`:

```python
UserConfig(user_id="team_5", password="pass005", starting_cash=100_000)
```

## Notebook Usage

`contest_demo.ipynb` is a notebook-friendly wrapper around the same engine. Use it if you want to demonstrate the simulator interactively, inspect intermediate outputs, or adapt the contest setup in cells.

The notebook imports from `simulator_engine.py`, so improvements to the engine automatically carry over to the notebook.

## Current Limitations

This is a mock contest simulator, not a production trading platform. It currently does not include:

- a persistent database,
- a live Gmail polling loop,
- a deployed API server,
- authentication beyond simple contest passwords,
- real market data,
- real order books or partial fills.

Those can be added later as adapters around the existing simulator core.

## Security

Do not hard-code Gmail passwords or OpenAI API keys in notebooks or source code. Pass credentials through environment variables or a separate secrets manager.

This repository is intended for mock trading contests only. Do not use it for real-money trading.
