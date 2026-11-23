from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
import math
import random
import re
from typing import Iterable


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class EmailKind(str, Enum):
    TRADE_ORDER = "TRADE_ORDER"
    MARKET_SIGNAL = "MARKET_SIGNAL"
    STOP = "STOP"
    OTHER = "OTHER"


@dataclass(frozen=True)
class StockConfig:
    ticker: str
    name: str
    initial_price: float
    shares_outstanding: int
    annual_drift: float = 0.06
    annual_volatility: float = 0.25


@dataclass(frozen=True)
class UserConfig:
    user_id: str
    password: str
    starting_cash: float = 100_000.0


@dataclass(frozen=True)
class EmailMessage:
    message_id: str
    subject: str
    body: str
    sender: str | None = None


@dataclass(frozen=True)
class TradeOrder:
    user_id: str
    password: str
    ticker: str
    quantity: int
    side: OrderSide
    source_message_id: str | None = None


@dataclass(frozen=True)
class MarketSignal:
    ticker: str
    sentiment: float
    volatility_multiplier: float = 1.0
    confidence: float = 1.0


@dataclass
class StockState:
    ticker: str
    name: str
    price: float
    shares_outstanding: int
    annual_drift: float
    annual_volatility: float
    sentiment: float = 0.0
    volatility_multiplier: float = 1.0
    price_history: list[float] = field(default_factory=list)

    @classmethod
    def from_config(cls, config: StockConfig) -> "StockState":
        return cls(
            ticker=config.ticker.upper(),
            name=config.name,
            price=float(config.initial_price),
            shares_outstanding=config.shares_outstanding,
            annual_drift=config.annual_drift,
            annual_volatility=config.annual_volatility,
            price_history=[float(config.initial_price)],
        )


@dataclass
class Holding:
    quantity: int = 0
    average_cost: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class Portfolio:
    user_id: str
    password: str
    cash: float
    holdings: dict[str, Holding] = field(default_factory=dict)
    trade_history: list["TradeResult"] = field(default_factory=list)

    def market_value(self, prices: dict[str, float]) -> float:
        return sum(
            holding.quantity * prices[ticker]
            for ticker, holding in self.holdings.items()
            if holding.quantity > 0 and ticker in prices
        )

    def total_value(self, prices: dict[str, float]) -> float:
        return self.cash + self.market_value(prices)

    def unrealized_pnl(self, prices: dict[str, float]) -> float:
        return sum(
            (prices[ticker] - holding.average_cost) * holding.quantity
            for ticker, holding in self.holdings.items()
            if holding.quantity > 0 and ticker in prices
        )

    def realized_pnl(self) -> float:
        return sum(holding.realized_pnl for holding in self.holdings.values())


@dataclass(frozen=True)
class TradeResult:
    accepted: bool
    message: str
    order: TradeOrder
    fill_price: float | None = None
    cash_after: float | None = None


class GBMPriceEngine:
    """Geometric Brownian motion price engine with sentiment-adjusted drift."""

    def __init__(
        self,
        rng: random.Random | None = None,
        trading_days_per_year: int = 252,
        sentiment_drift_weight: float = 0.18,
        sentiment_decay: float = 0.85,
    ) -> None:
        self.rng = rng or random.Random()
        self.trading_days_per_year = trading_days_per_year
        self.sentiment_drift_weight = sentiment_drift_weight
        self.sentiment_decay = sentiment_decay

    def step(self, stock: StockState, days: float = 1.0) -> float:
        if stock.price <= 0:
            raise ValueError(f"{stock.ticker} has a non-positive price.")

        dt = days / self.trading_days_per_year
        mu = stock.annual_drift + self.sentiment_drift_weight * stock.sentiment
        sigma = max(0.0001, stock.annual_volatility * stock.volatility_multiplier)
        z = self.rng.gauss(0.0, 1.0)
        next_price = stock.price * math.exp((mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z)
        stock.price = max(0.01, next_price)
        stock.price_history.append(stock.price)
        stock.sentiment *= self.sentiment_decay
        stock.volatility_multiplier = 1.0 + (stock.volatility_multiplier - 1.0) * self.sentiment_decay
        return stock.price


class PortfolioManager:
    def __init__(self, users: Iterable[UserConfig]) -> None:
        self.portfolios = {
            str(user.user_id): Portfolio(
                user_id=str(user.user_id),
                password=str(user.password),
                cash=float(user.starting_cash),
            )
            for user in users
        }

    def execute(self, order: TradeOrder, prices: dict[str, float]) -> TradeResult:
        portfolio = self.portfolios.get(str(order.user_id))
        if portfolio is None:
            return TradeResult(False, f"Rejected: unknown portfolio {order.user_id}.", order)

        if portfolio.password != str(order.password):
            return TradeResult(False, f"Rejected: bad password for portfolio {order.user_id}.", order)

        if order.quantity <= 0:
            return TradeResult(False, "Rejected: quantity must be positive.", order)

        ticker = order.ticker.upper()
        price = prices.get(ticker)
        if price is None:
            return TradeResult(False, f"Rejected: unknown stock {ticker}.", order)

        if order.side is OrderSide.BUY:
            result = self._buy(portfolio, order, price)
        else:
            result = self._sell(portfolio, order, price)

        portfolio.trade_history.append(result)
        return result

    def _buy(self, portfolio: Portfolio, order: TradeOrder, price: float) -> TradeResult:
        cost = order.quantity * price
        if portfolio.cash + 1e-9 < cost:
            return TradeResult(False, "Rejected: insufficient cash.", order, fill_price=price, cash_after=portfolio.cash)

        holding = portfolio.holdings.setdefault(order.ticker.upper(), Holding())
        previous_cost = holding.average_cost * holding.quantity
        holding.quantity += order.quantity
        holding.average_cost = (previous_cost + cost) / holding.quantity
        portfolio.cash -= cost
        return TradeResult(True, f"Bought {order.quantity} {order.ticker.upper()} at {price:.2f}.", order, price, portfolio.cash)

    def _sell(self, portfolio: Portfolio, order: TradeOrder, price: float) -> TradeResult:
        holding = portfolio.holdings.get(order.ticker.upper())
        if holding is None or holding.quantity < order.quantity:
            return TradeResult(False, "Rejected: insufficient shares.", order, fill_price=price, cash_after=portfolio.cash)

        proceeds = order.quantity * price
        holding.quantity -= order.quantity
        holding.realized_pnl += (price - holding.average_cost) * order.quantity
        portfolio.cash += proceeds
        if holding.quantity == 0:
            holding.average_cost = 0.0
        return TradeResult(True, f"Sold {order.quantity} {order.ticker.upper()} at {price:.2f}.", order, price, portfolio.cash)

    def leaderboard(self, prices: dict[str, float]) -> list[dict[str, float | int | str]]:
        rows = []
        for portfolio in self.portfolios.values():
            rows.append(
                {
                    "user_id": portfolio.user_id,
                    "cash": round(portfolio.cash, 2),
                    "market_value": round(portfolio.market_value(prices), 2),
                    "total_value": round(portfolio.total_value(prices), 2),
                    "realized_pnl": round(portfolio.realized_pnl(), 2),
                    "unrealized_pnl": round(portfolio.unrealized_pnl(prices), 2),
                }
            )
        rows.sort(key=lambda row: row["total_value"], reverse=True)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        return rows


class EmailOrderParser:
    def __init__(
        self,
        aliases: dict[str, str] | None = None,
        fuzzy_match_threshold: float = 0.84,
        fuzzy_match_margin: float = 0.08,
    ) -> None:
        self.aliases = {key.lower(): value.upper() for key, value in (aliases or {}).items()}
        self.fuzzy_match_threshold = fuzzy_match_threshold
        self.fuzzy_match_margin = fuzzy_match_margin

    def classify(self, email_message: EmailMessage) -> EmailKind:
        subject = email_message.subject.lower()
        if "stop simulation" in subject or "stop" == subject.strip():
            return EmailKind.STOP
        if "crisis" in subject or "signal" in subject or "news" in subject:
            return EmailKind.MARKET_SIGNAL
        if "trade" in subject or any(word in email_message.body.lower() for word in ("buy", "sell")):
            return EmailKind.TRADE_ORDER
        return EmailKind.OTHER

    def parse_trade(self, email_message: EmailMessage) -> TradeOrder | None:
        text = email_message.body.strip()
        fields = self._parse_labeled_fields(text)

        side_text = fields.get("action") or fields.get("side") or fields.get("buy/sell")
        stock_text = fields.get("stock") or fields.get("ticker")
        quantity_text = fields.get("quantity") or fields.get("shares")
        user_text = fields.get("portfolio") or fields.get("user") or fields.get("user_id")
        password_text = fields.get("password")

        if not all([side_text, stock_text, quantity_text, user_text, password_text]):
            inferred = self._parse_sentence(text)
            stock_text = stock_text or inferred.get("stock")
            quantity_text = quantity_text or inferred.get("quantity")
            user_text = user_text or inferred.get("portfolio")
            password_text = password_text or inferred.get("password")
            side_text = side_text or inferred.get("action")

        if not all([side_text, stock_text, quantity_text, user_text, password_text]):
            return None

        side = self._parse_side(side_text)
        ticker = self._normalize_ticker(stock_text)
        quantity = self._parse_int(quantity_text)
        if side is None or ticker is None or quantity is None:
            return None

        return TradeOrder(
            user_id=str(user_text).strip(),
            password=str(password_text).strip(),
            ticker=ticker,
            quantity=quantity,
            side=side,
            source_message_id=email_message.message_id,
        )

    def _parse_labeled_fields(self, text: str) -> dict[str, str]:
        fields = {}
        for match in re.finditer(r"(?im)^\s*([a-z_/ -]+)\s*:\s*(.+?)\s*$", text):
            key = match.group(1).strip().lower().replace(" ", "_")
            fields[key] = match.group(2).strip()
        return fields

    def _parse_sentence(self, text: str) -> dict[str, str]:
        lowered = text.lower()
        fields = {}

        action_match = re.search(r"\b(buy|sell|purchase|long|dump)\b", lowered)
        if action_match:
            fields["action"] = action_match.group(1)

        quantity_match = re.search(r"\b(\d{1,9})\s*(?:shares?|units?)\b", lowered)
        if quantity_match is None:
            quantity_match = re.search(r"\b(?:buy|sell|purchase|long|dump)\s+(\d{1,9})\b", lowered)
        if quantity_match:
            fields["quantity"] = quantity_match.group(1)

        portfolio_match = re.search(r"\b(?:portfolio|user|id)\s*#?\s*(\w+)\b", lowered)
        if portfolio_match:
            fields["portfolio"] = portfolio_match.group(1)

        password_match = re.search(r"\bpassword\s*(?:is|=|:)?\s*([A-Za-z0-9_-]+)\b", text, re.IGNORECASE)
        if password_match:
            fields["password"] = password_match.group(1)

        for alias in sorted(self.aliases, key=len, reverse=True):
            if alias in lowered:
                fields["stock"] = alias
                break

        if "stock" not in fields:
            fuzzy_stock = self._find_fuzzy_stock_mention(text)
            if fuzzy_stock:
                fields["stock"] = fuzzy_stock

        if "stock" not in fields:
            ticker_match = re.search(r"\b([A-Z]{2,5})\b", text)
            if ticker_match:
                fields["stock"] = ticker_match.group(1)

        return fields

    def _parse_side(self, value: str) -> OrderSide | None:
        normalized = str(value).strip().lower()
        if normalized in {"1", "+1", "buy", "b", "purchase", "long"}:
            return OrderSide.BUY
        if normalized in {"-1", "sell", "s", "short", "dump"}:
            return OrderSide.SELL
        return None

    def _normalize_ticker(self, value: str) -> str | None:
        cleaned = re.sub(r"[^A-Za-z0-9 -]", "", str(value)).strip()
        if not cleaned:
            return None
        normalized = cleaned.lower()
        if normalized in self.aliases:
            return self.aliases[normalized]

        ticker = cleaned.upper().replace(" ", "")
        known_tickers = set(self.aliases.values())
        if ticker in known_tickers:
            return ticker

        return self._best_fuzzy_ticker(normalized) or ticker

    def _find_fuzzy_stock_mention(self, text: str) -> str | None:
        lowered = re.sub(r"[^a-z0-9 ]", " ", text.lower())
        words = lowered.split()
        if not words:
            return None

        best_alias = None
        best_score = 0.0
        second_score = 0.0
        for alias in self.aliases:
            alias_words = alias.split()
            window_sizes = {max(1, len(alias_words) - 1), len(alias_words), len(alias_words) + 1}
            for size in window_sizes:
                if size > len(words):
                    continue
                for start in range(0, len(words) - size + 1):
                    phrase = " ".join(words[start : start + size])
                    score = SequenceMatcher(None, phrase, alias).ratio()
                    if score > best_score:
                        second_score = best_score
                        best_score = score
                        best_alias = alias
                    elif score > second_score:
                        second_score = score

        if best_alias and self._is_confident_fuzzy_match(best_score, second_score):
            return best_alias
        return None

    def _best_fuzzy_ticker(self, value: str) -> str | None:
        candidates = list(self.aliases) + list(set(self.aliases.values()))
        scored = sorted(
            ((SequenceMatcher(None, value.lower(), candidate.lower()).ratio(), candidate) for candidate in candidates),
            reverse=True,
        )
        if not scored:
            return None

        best_score, best_candidate = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if not self._is_confident_fuzzy_match(best_score, second_score):
            return None

        return self.aliases.get(best_candidate.lower(), best_candidate.upper())

    def _is_confident_fuzzy_match(self, best_score: float, second_score: float) -> bool:
        return (
            best_score >= self.fuzzy_match_threshold
            and best_score - second_score >= self.fuzzy_match_margin
        )

    def _parse_int(self, value: str) -> int | None:
        try:
            parsed = int(str(value).replace(",", "").strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None


class ContestSimulator:
    def __init__(
        self,
        stocks: Iterable[StockConfig],
        users: Iterable[UserConfig],
        seed: int | None = None,
    ) -> None:
        self.rng = random.Random(seed)
        self.stocks = {stock.ticker.upper(): StockState.from_config(stock) for stock in stocks}
        self.price_engine = GBMPriceEngine(self.rng)
        self.portfolios = PortfolioManager(users)
        self.processed_message_ids: set[str] = set()

    def current_prices(self) -> dict[str, float]:
        return {ticker: stock.price for ticker, stock in self.stocks.items()}

    def submit_order(self, order: TradeOrder) -> TradeResult:
        if order.source_message_id and order.source_message_id in self.processed_message_ids:
            return TradeResult(False, f"Rejected: duplicate message {order.source_message_id}.", order)

        result = self.portfolios.execute(order, self.current_prices())
        if order.source_message_id:
            self.processed_message_ids.add(order.source_message_id)
        return result

    def apply_market_signals(self, signals: Iterable[MarketSignal]) -> None:
        for signal in signals:
            stock = self.stocks.get(signal.ticker.upper())
            if stock is None:
                continue
            confidence = min(1.0, max(0.0, signal.confidence))
            sentiment = min(1.0, max(-1.0, signal.sentiment))
            stock.sentiment = 0.65 * stock.sentiment + 0.35 * sentiment * confidence
            stock.volatility_multiplier = max(
                0.2,
                stock.volatility_multiplier * (1.0 + (signal.volatility_multiplier - 1.0) * confidence),
            )

    def tick(self, days: float = 1.0) -> dict[str, float]:
        return {ticker: self.price_engine.step(stock, days=days) for ticker, stock in self.stocks.items()}

    def price_table(self) -> list[dict[str, float | str]]:
        return [
            {
                "ticker": stock.ticker,
                "name": stock.name,
                "price": round(stock.price, 2),
                "sentiment": round(stock.sentiment, 3),
                "volatility_multiplier": round(stock.volatility_multiplier, 3),
            }
            for stock in self.stocks.values()
        ]

    def leaderboard(self) -> list[dict[str, float | int | str]]:
        return self.portfolios.leaderboard(self.current_prices())
