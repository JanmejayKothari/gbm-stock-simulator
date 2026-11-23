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
├── demo.py                          # Runnable script demo
├── contest_demo.ipynb               # Notebook demo/workspace
├── tests/
│   └── test_stock_simulator.py      # Unit tests
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

## Contest Manager Workflow

The current version is best understood as a contest engine plus demo workspace. It does not run a fully automated live contest by itself. A contest manager, teacher, organizer, or future adapter is expected to control when messages are processed, when crises are applied, and when the market advances.

### 1. Set up the contest universe

Before the contest starts, the contest manager defines:

- the available stocks,
- each stock's starting price,
- each stock's annual drift and volatility if custom values are needed,
- participating teams/users,
- each team's starting cash,
- each team's password or access code,
- aliases for company names participants may type in trades.

This setup currently happens in `demo.py` or `contest_demo.ipynb`:

```python
simulator = ContestSimulator(
    stocks=[
        StockConfig("AAA", "Alpha Corp", initial_price=10.0, shares_outstanding=50_000),
        StockConfig("BBB", "Beta Corp", initial_price=10.0, shares_outstanding=50_000),
    ],
    users=[
        UserConfig("team_1", "pass001", starting_cash=100_000),
        UserConfig("team_2", "pass002", starting_cash=100_000),
    ],
)
```

### 2. Collect participant trades

Participants can submit trade-style messages. In the demo, these are represented with `EmailMessage` objects. In a live deployment, a Gmail/IMAP adapter could fetch real emails and convert them into the same object shape.

The simulator supports both structured and sentence-style orders. The contest manager should tell participants what format to use and what portfolio ID/password they have.

Recommended structured format:

```text
stock: AAA
quantity: 100
portfolio: team_1
password: pass001
buy/sell: +1
```

Sentence-style orders can also work:

```text
Portfolio team_1 password pass001 wants to buy 100 shares of Alpha Corp.
```

The parser includes conservative fuzzy matching for stock names, so obvious typos can be corrected. Ambiguous or incomplete trades are rejected.

### 3. Process trades

For each trade message, the contest runner should:

1. classify the message,
2. parse it into a `TradeOrder`,
3. submit the order to the simulator,
4. record or display the acceptance/rejection message.

Example:

```python
kind = parser.classify(email)

if kind is EmailKind.TRADE_ORDER:
    order = parser.parse_trade(email)
    if order is None:
        print("Rejected: could not parse order")
    else:
        result = simulator.submit_order(order)
        print(result.message)
```

Accepted trades execute at the current simulated market price. Rejected trades do not change cash, holdings, prices, or leaderboard values.

### 4. Apply crises or news events

Crisis/news events are not automatically interpreted by the engine from plain English in the current version. The contest manager must decide which stocks are affected and provide one or more `MarketSignal` objects.

Example:

```python
simulator.apply_market_signals([
    MarketSignal("BBB", sentiment=-0.45, volatility_multiplier=1.4, confidence=0.8),
    MarketSignal("CCC", sentiment=0.70, volatility_multiplier=1.2, confidence=0.9),
])
```

Signal fields:

- `ticker`: stock affected by the event.
- `sentiment`: direction of the effect, from negative to positive. Use values around `-1.0` to `1.0`.
- `volatility_multiplier`: how much more or less volatile the stock becomes. Values above `1.0` increase volatility.
- `confidence`: how strongly the signal should be applied, from `0.0` to `1.0`.

The engine then folds the signal into the stock's drift and volatility. The effect decays over later price ticks.

If you want automated crisis interpretation, add an adapter outside the engine that turns a crisis email body into `MarketSignal` objects. For example, an LLM adapter could read:

```text
A port strike disrupts shipping and logistics companies.
```

and output:

```python
[MarketSignal("BBB", sentiment=-0.7, volatility_multiplier=1.6, confidence=0.85)]
```

The core engine intentionally does not hard-code this LLM behavior.

### 5. Advance the market

The contest manager decides when simulated time advances. For example, call this once after a batch of trades, once per round, or once per real-world day:

```python
simulator.tick(days=1)
```

Each tick updates prices using geometric Brownian motion plus any active sentiment/volatility effects.

### 6. Publish prices and leaderboard

After processing trades and advancing the market, the contest manager can show current prices:

```python
simulator.price_table()
```

and rankings:

```python
simulator.leaderboard()
```

The leaderboard ranks by:

```text
cash + market value of current holdings
```

### Recommended round structure

For a classroom or live contest, a simple round can look like this:

```text
1. Contest manager announces current prices and leaderboard.
2. Participants submit trade emails/messages.
3. Contest manager processes all trade messages.
4. Contest manager optionally introduces a crisis/news event.
5. Contest manager applies MarketSignal objects for that crisis.
6. Contest manager advances the market with simulator.tick(days=1).
7. Contest manager publishes updated prices and leaderboard.
8. Repeat for the next round.
```

### What is automated right now

The engine currently automates:

- parsing trade-style messages,
- correcting obvious stock-name typos,
- validating trades,
- executing buys and sells,
- updating cash and holdings,
- tracking P&L,
- simulating prices with GBM,
- applying provided market signals,
- ranking portfolios.

### What the contest manager or adapter must currently provide

The contest manager or a future adapter must provide:

- the contest universe and users,
- incoming messages,
- when to process messages,
- crisis-to-`MarketSignal` interpretation,
- when to advance time,
- where to display or persist results.

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

## License

This project is licensed under the MIT License. See `LICENSE` for details.
