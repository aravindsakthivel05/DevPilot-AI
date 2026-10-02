import unittest

from parcel.api import shipping_quote


class PricingTests(unittest.TestCase):
    def test_international_quote(self):
        self.assertEqual(shipping_quote(2, "international")["amount"], 24.0)

    def test_minimum(self):
        self.assertEqual(shipping_quote(0.5, "domestic")["amount"], 10.0)

    def test_invalid_weight(self):
        with self.assertRaises(ValueError):
            shipping_quote(-1, "domestic")
