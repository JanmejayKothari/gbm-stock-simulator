from stock_simulator import (
    ContestSimulator,
    EmailMessage,
    EmailOrderParser,
    MarketSignal,
    StockConfig,
    UserConfig,
)


def main() -> None:
    simulator = ContestSimulator(
        stocks=[
            StockConfig("AAA", "Alpha Corp", initial_price=10.0, shares_outstanding=50_000),
            StockConfig("BBB", "Beta Corp", initial_price=10.0, shares_outstanding=50_000),
            StockConfig("CCC", "Gamma Corp", initial_price=10.0, shares_outstanding=50_000),
            StockConfig("DDD", "Delta Corp", initial_price=10.0, shares_outstanding=50_000),
        ],
        users=[
            UserConfig(user_id="team_1", password="pass001", starting_cash=100_000),
            UserConfig(user_id="team_2", password="pass002", starting_cash=100_000),
            UserConfig(user_id="team_3", password="pass003", starting_cash=100_000),
            UserConfig(user_id="team_4", password="pass004", starting_cash=100_000),
        ],
        seed=7,
    )

    parser = EmailOrderParser(
        aliases={
            "alpha corp": "AAA",
            "beta corp": "BBB",
            "gamma corp": "CCC",
            "delta corp": "DDD",
        }
    )

    emails = [
        EmailMessage(
            message_id="m1",
            subject="trade",
            body="Portfolio team_1 password pass001 wants to buy 100 shares of Alhpa Corp.",
        ),
        EmailMessage(
            message_id="m2",
            subject="trade",
            body="portfolio: team_2\npassword: pass002\naction: buy\nstock: BBB\nquantity: 250",
        ),
        EmailMessage(
            message_id="m3",
            subject="crisis",
            body="Rail and tram transport companies face uncertainty, while battlefield medicine demand rises.",
        ),
    ]

    signals = {
        "m3": [
            MarketSignal("BBB", sentiment=-0.45, volatility_multiplier=1.4, confidence=0.8),
            MarketSignal("CCC", sentiment=0.70, volatility_multiplier=1.2, confidence=0.9),
        ]
    }

    for email in emails:
        if parser.classify(email) == "MARKET_SIGNAL":
            simulator.apply_market_signals(signals[email.message_id])
            print(f"Applied market signal from {email.message_id}")
            continue

        order = parser.parse_trade(email)
        if order is None:
            print(f"Ignored {email.message_id}")
            continue

        result = simulator.submit_order(order)
        print(result.message)

    simulator.tick(days=1)

    print("\nPrices")
    for row in simulator.price_table():
        print(row)

    print("\nLeaderboard")
    for row in simulator.leaderboard():
        print(row)


if __name__ == "__main__":
    main()
