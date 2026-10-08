import argparse
import json
import subprocess
import unittest
from unittest.mock import patch

import iproyal as api


class FakeClient:
    def __init__(self, price=5, balance=20):
        self.calls = []
        self.price = price
        self.balance = balance

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        if path == "/products":
            return {"data": [{"id": 9, "name": "ISP", "plans": [{"id": 22, "name": "30 Days", "min_quantity": 1, "max_quantity": 10}],
                              "locations": [{"id": 27, "name": "Singapore", "out_of_stock": False}], "questions": []}]}
        if path == "/orders/calculate-pricing":
            return {"price_with_vat": self.price}
        if path == "/balance":
            return self.balance
        raise AssertionError(path)

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        return {"id": 123, "status": "confirmed", "proxy_data": {"proxies": [{"ip": "192.0.2.5", "password": "SECRET"}]}}


def args(**changes):
    result = dict(product_id=9, plan_id=22, location_id=27, quantity=1,
                  answers_file=None, coupon=None, auto_extend=False, execute=False, max_total=None)
    result.update(changes)
    return argparse.Namespace(**result)


class SafetyTests(unittest.TestCase):
    def test_order_summary_suppresses_credentials_and_free_text(self):
        raw = {"id": 1, "note": "SECRET", "questions_answers": ["SECRET"],
               "unknown": "SECRET", "proxy_data": {"proxies": [{"ip": "192.0.2.1", "username": "SECRET", "password": "SECRET"}]},
               "auto_extend_settings": {"is_enabled": True, "password": "SECRET"}}
        output = json.dumps(api.order_summary(raw))
        self.assertNotIn("SECRET", output)
        self.assertIn("192.0.2.1", output)

    def test_dry_run_performs_no_post(self):
        client = FakeClient()
        result = api.purchase(client, args())
        self.assertFalse(result["executed"])
        self.assertTrue(all(c[0] == "GET" for c in client.calls))

    def test_execute_needs_cap_before_network(self):
        client = FakeClient()
        with self.assertRaises(api.ApiError):
            api.purchase(client, args(execute=True))
        self.assertEqual(client.calls, [])

    def test_price_and_balance_guards_prevent_post(self):
        for client, options in [(FakeClient(price=6), args(execute=True, max_total="5")),
                                (FakeClient(balance=1), args(execute=True, max_total="5"))]:
            with self.assertRaises(api.ApiError):
                api.purchase(client, options)
            self.assertTrue(all(c[0] == "GET" for c in client.calls))

    def test_invalid_or_nonfinite_price_never_purchases(self):
        for price in [None, "NaN", "Infinity", "-1"]:
            client = FakeClient(price=price)
            with self.assertRaises(api.ApiError):
                api.purchase(client, args(execute=True, max_total="10"))
            self.assertTrue(all(c[0] == "GET" for c in client.calls))

    def test_unknown_plan_or_location_prevents_post(self):
        for options in [args(plan_id=999), args(location_id=999), args(quantity=100)]:
            client = FakeClient()
            with self.assertRaises(api.ApiError):
                api.purchase(client, options)
            self.assertTrue(all(c[0] == "GET" for c in client.calls))

    def test_authorized_execute_posts_once_and_no_recurring_default(self):
        client = FakeClient()
        result = api.purchase(client, args(execute=True, max_total="5"))
        posts = [c for c in client.calls if c[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertFalse(posts[0][2]["auto_extend"])
        self.assertNotIn("card_id", posts[0][2])
        self.assertTrue(result["executed"])
        self.assertNotIn("SECRET", json.dumps(result))

    @patch("iproyal.subprocess.run")
    def test_transport_does_not_leak_token_and_never_retries_post(self, run):
        run.return_value = subprocess.CompletedProcess([], 28, "", "SECRET")
        with self.assertRaises(api.ApiError) as ctx:
            api.Client("SECRET").request("POST", "/orders", body={"quantity": 1})
        self.assertEqual(run.call_count, 1)
        self.assertNotIn("SECRET", str(ctx.exception))
        self.assertIn("unknown", str(ctx.exception))
        self.assertNotIn("SECRET", json.dumps(run.call_args.args))

    @patch("iproyal.subprocess.run")
    def test_error_response_body_never_printed(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '{"password":"SECRET"}\n422', "")
        with self.assertRaises(api.ApiError) as ctx:
            api.Client("TOKEN").get("/orders")
        self.assertNotIn("SECRET", str(ctx.exception))
        self.assertIn("422", str(ctx.exception))

    def test_quote_has_no_execute_option(self):
        with self.assertRaises(SystemExit):
            api.parser().parse_args(["quote", "--execute", "--product-id", "9", "--plan-id", "22", "--location-id", "27", "--quantity", "1"])


if __name__ == "__main__":
    unittest.main()
