import unittest

from stock_simulator import (
    ContestSimulator,
    EmailMessage,
    EmailOrderParser,
    EmailKind,
    MarketSignal,
    OrderSide,
    StockConfig,
    TradeOrder,
    UserConfig,
)


class StockSimulatorTests(unittest.TestCase):
    def make_simulator(self):
        return ContestSimulator(
            stocks=[StockConfig("AAA", "Alpha Corp", 10.0, 50_000)],
            users=[UserConfig("team_1", "pw", 1_000.0)],
            seed=1,
        )

    def test_buy_updates_cash_and_holdings(self):
        simulator = self.make_simulator()
        result = simulator.submit_order(TradeOrder("team_1", "pw", "AAA", 10, OrderSide.BUY))

        self.assertTrue(result.accepted)
        portfolio = simulator.portfolios.portfolios["team_1"]
        self.assertEqual(portfolio.holdings["AAA"].quantity, 10)
        self.assertAlmostEqual(portfolio.cash, 900.0)

    def test_rejects_oversell(self):
        simulator = self.make_simulator()
        result = simulator.submit_order(TradeOrder("team_1", "pw", "AAA", 1, OrderSide.SELL))

        self.assertFalse(result.accepted)
        self.assertIn("insufficient shares", result.message)

    def test_gbm_tick_changes_price_and_keeps_positive(self):
        simulator = self.make_simulator()
        before = simulator.current_prices()["AAA"]
        after = simulator.tick()["AAA"]

        self.assertNotEqual(before, after)
        self.assertGreater(after, 0)

    def test_market_signal_changes_sentiment(self):
        simulator = self.make_simulator()
        simulator.apply_market_signals([MarketSignal("AAA", sentiment=1.0, confidence=1.0)])

        self.assertGreater(simulator.stocks["AAA"].sentiment, 0)

    def test_labeled_email_order_parser(self):
        parser = EmailOrderParser()
        email = EmailMessage(
            "m1",
            "trade",
            "stock: AAA\nquantity: 25\nportfolio: team_1\npassword: pw\nbuy/sell: +1",
        )

        order = parser.parse_trade(email)

        self.assertIsNotNone(order)
        self.assertEqual(order.ticker, "AAA")
        self.assertEqual(order.quantity, 25)
        self.assertEqual(order.side, OrderSide.BUY)

    def test_sentence_email_order_parser_with_alias(self):
        parser = EmailOrderParser({"alpha corp": "AAA"})
        email = EmailMessage("m1", "trade", "Portfolio team_1 password pw wants to buy 12 shares of Alpha Corp.")

        order = parser.parse_trade(email)

        self.assertIsNotNone(order)
        self.assertEqual(order.ticker, "AAA")
        self.assertEqual(order.quantity, 12)
        self.assertEqual(order.user_id, "team_1")

    def test_email_order_parser_corrects_obvious_stock_typo(self):
        parser = EmailOrderParser({"alpha corp": "AAA", "beta corp": "BBB"})
        email = EmailMessage("m1", "trade", "Portfolio team_1 password pw wants to buy 12 shares of Alhpa Corp.")

        order = parser.parse_trade(email)

        self.assertIsNotNone(order)
        self.assertEqual(order.ticker, "AAA")

    def test_email_order_parser_rejects_weak_stock_typo(self):
        parser = EmailOrderParser({"alpha corp": "AAA", "beta corp": "BBB"})
        email = EmailMessage("m1", "trade", "Portfolio team_1 password pw wants to buy 12 shares of Mystery Company.")

        order = parser.parse_trade(email)

        self.assertIsNone(order)

    def test_email_classification(self):
        parser = EmailOrderParser()

        self.assertEqual(parser.classify(EmailMessage("m1", "crisis", "news")), EmailKind.MARKET_SIGNAL)
        self.assertEqual(parser.classify(EmailMessage("m2", "stop simulation", "")), EmailKind.STOP)


if __name__ == "__main__":
    unittest.main()
