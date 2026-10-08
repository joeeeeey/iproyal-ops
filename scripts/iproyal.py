#!/usr/bin/env python3
"""Credential-safe IPRoyal inspection and explicit balance-funded purchases."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

BASE = "https://apid.iproyal.com/v1/reseller"
STATUSES = ("unpaid", "in-progress", "confirmed", "refunded", "expired")


class ApiError(Exception):
    pass


def load_token():
    token = os.environ.get("IPROYAL_API_TOKEN")
    if not token:
        path = Path(os.environ.get("IPROYAL_TOKEN_FILE", "~/.config/iproyal/token")).expanduser()
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ApiError("Token file must be owned by the current user and mode 0600")
        token = path.read_text().strip()
    if not token or any(c.isspace() for c in token):
        raise ApiError("Missing or invalid API token")
    return token


def flatten_query(value, prefix=""):
    pairs = []
    for key, item in value.items():
        name = f"{prefix}[{key}]" if prefix else key
        if isinstance(item, dict):
            pairs.extend(flatten_query(item, name))
        elif item is not None:
            pairs.append((name, str(item).lower() if isinstance(item, bool) else str(item)))
    return pairs


class Client:
    def __init__(self, token=None):
        self.token = token if token is not None else load_token()

    def request(self, method, path, params=None, body=None):
        if method not in ("GET", "POST") or not path.startswith("/") or "?" in path or "#" in path:
            raise ApiError("Invalid API request")
        url = BASE + path
        if params:
            url += "?" + urlencode(flatten_query(params))
        # Config and JSON body use stdin, so tokens never occur in argv or output.
        config = "\n".join([
            "url = " + json.dumps(url),
            "request = " + json.dumps(method),
            "header = " + json.dumps("X-Access-Token: " + self.token),
            'header = "Accept: application/json"',
            'header = "Content-Type: application/json"',
        ]) + "\n"
        if body is not None:
            config += "data = " + json.dumps(json.dumps(body)) + "\n"
        try:
            result = subprocess.run(
                ["curl", "--disable", "--config", "-", "--proto", "=https", "--silent",
                 "--show-error", "--max-time", "30", "--write-out", "\n%{http_code}"],
                input=config, capture_output=True, text=True, timeout=35,
            )
        except (subprocess.TimeoutExpired, OSError):
            raise ApiError(self.failure(method, "Transport failure")) from None
        if result.returncode:
            raise ApiError(self.failure(method, "Transport failure"))
        try:
            text, raw_status = result.stdout.rsplit("\n", 1)
            status_code = int(raw_status)
        except ValueError:
            raise ApiError(self.failure(method, "Invalid HTTP response")) from None
        if not 200 <= status_code < 300:
            raise ApiError(self.failure(method, f"API HTTP {status_code}; response body suppressed"))
        try:
            return json.loads(text)
        except ValueError:
            raise ApiError(self.failure(method, "API returned invalid JSON")) from None

    @staticmethod
    def failure(method, message):
        if method == "POST":
            return message + "; purchase outcome may be unknown. Inspect orders/balance before retrying."
        return message

    def get(self, path, params=None):
        return self.request("GET", path, params=params)


def select(obj, keys):
    return {key: obj[key] for key in keys if key in obj}


def order_summary(order):
    # Allowlist: do not emit arbitrary notes, answers, history, or proxy credentials.
    out = select(order, ("id", "product_name", "plan_name", "expire_date", "status", "location", "locations", "quantity", "is_test"))
    proxy = order.get("proxy_data") or {}
    out["proxy_ips"] = [p["ip"] for p in proxy.get("proxies", []) if isinstance(p, dict) and "ip" in p]
    auto = order.get("auto_extend_settings")
    out["auto_extend"] = select(auto, ("is_enabled", "payment_type")) if isinstance(auto, dict) else None
    return out


def location_tree(locations):
    for location in locations:
        yield location
        yield from location_tree(location.get("child_locations", []))


def product_summary(product, location_search=None):
    out = select(product, ("id", "name", "plans", "questions", "quantity_discounts"))
    locations = product.get("locations", [])
    if location_search:
        locations = [l for l in locations if any(location_search.casefold() in str(x.get("name", "")).casefold()
                     for x in location_tree([l]))]
    out["locations"] = locations
    return out


def money(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ApiError("Invalid monetary amount") from None
    if not number.is_finite() or number < 0:
        raise ApiError("Monetary amounts must be finite and nonnegative")
    return number


def prepare_purchase(client, args):
    catalog = client.get("/products")["data"]
    product = next((p for p in catalog if p["id"] == args.product_id), None)
    if product is None:
        raise ApiError("Product ID not in current catalog")
    plan = next((p for p in product.get("plans", []) if p["id"] == args.plan_id), None)
    location = next((l for l in location_tree(product.get("locations", [])) if l["id"] == args.location_id), None)
    if plan is None or location is None:
        raise ApiError("Plan/location does not belong to this product")
    if location.get("out_of_stock"):
        raise ApiError("Location is out of stock")
    if args.quantity < (plan.get("min_quantity") or 1) or args.quantity > (plan.get("max_quantity") or sys.maxsize):
        raise ApiError("Quantity is outside current plan limits")
    answers = {}
    if args.answers_file:
        try:
            answers = json.loads(Path(args.answers_file).read_text())
        except (OSError, ValueError):
            raise ApiError("Answers file must contain a JSON object") from None
        if not isinstance(answers, dict) or any(isinstance(v, (list, dict)) for v in answers.values()):
            raise ApiError("Answers must be a question-ID-to-scalar map")
    questions = {str(q["id"]): q for q in product.get("questions", [])}
    if any(k not in questions for k in answers):
        raise ApiError("Answer references an unknown question ID")
    for qid, question in questions.items():
        if question.get("is_required") and qid not in answers:
            raise ApiError(f"Required product question {qid} is unanswered")
        if qid in answers and question.get("type") == "select":
            if str(answers[qid]) not in {str(o["value"]) for o in question.get("options", [])}:
                raise ApiError(f"Invalid option for product question {qid}")
        if qid in answers and question.get("type") == "boolean" and not isinstance(answers[qid], bool):
            raise ApiError(f"Product question {qid} requires a boolean")
    payload = {"product_id": args.product_id, "product_plan_id": args.plan_id,
               "product_location_id": args.location_id, "quantity": args.quantity}
    if answers:
        payload["product_question_answers"] = answers
    if args.coupon:
        payload["coupon_code"] = args.coupon
    quote = client.get("/orders/calculate-pricing", payload)
    total = money(quote["price_with_vat"])
    balance = money(client.get("/balance"))
    payload["auto_extend"] = args.auto_extend
    preview = {"action": "create_order", "executed": False,
               "product": select(product, ("id", "name")), "plan": select(plan, ("id", "name")),
               "location": select(location, ("id", "name")), "quantity": args.quantity,
               "question_ids": sorted(answers), "coupon_supplied": bool(args.coupon),
               "auto_extend": args.auto_extend, "payment": "balance",
               "total_with_vat": str(total), "balance": str(balance),
               "sufficient_balance": balance >= total}
    return payload, preview, total, balance


def purchase(client, args):
    if args.execute and args.max_total is None:
        raise ApiError("--execute requires --max-total set to the user-approved total")
    cap = money(args.max_total) if args.max_total is not None else None
    payload, preview, total, balance = prepare_purchase(client, args)
    if not args.execute:
        return preview
    if total > cap:
        raise ApiError("Current quoted total exceeds approved --max-total; no purchase sent")
    if total > balance:
        raise ApiError("Insufficient balance; no purchase sent")
    order = client.request("POST", "/orders", body=payload)
    if not isinstance(order, dict) or not isinstance(order.get("id"), int):
        raise ApiError("Purchase response missing order ID; inspect orders before retrying")
    return {"executed": True, "order": order_summary(order)}


def positive(raw):
    try:
        value = int(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Must be a positive integer")


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("balance")
    products = sub.add_parser("products")
    products.add_argument("--product-id", type=positive)
    products.add_argument("--location-search")
    orders = sub.add_parser("orders")
    orders.add_argument("--product-id", required=True, type=positive)
    orders.add_argument("--page", type=positive, default=1)
    orders.add_argument("--per-page", type=positive, default=20)
    orders.add_argument("--status", choices=STATUSES)
    orders.add_argument("--location-id", type=positive)
    sub.add_parser("order").add_argument("order_id", type=positive)
    for name in ("quote", "create-order"):
        p = sub.add_parser(name)
        p.add_argument("--product-id", required=True, type=positive)
        p.add_argument("--plan-id", required=True, type=positive)
        p.add_argument("--location-id", required=True, type=positive)
        p.add_argument("--quantity", required=True, type=positive)
        p.add_argument("--coupon")
        p.add_argument("--answers-file")
        p.add_argument("--auto-extend", action="store_true")
        p.set_defaults(execute=False, max_total=None)
        if name == "create-order":
            p.add_argument("--execute", action="store_true")
            p.add_argument("--max-total")
    return root


def main():
    args = parser().parse_args()
    try:
        client = Client()
        if args.command == "balance":
            result = {"balance": str(money(client.get("/balance")))}
        elif args.command == "products":
            result = {"data": [product_summary(p, args.location_search) for p in client.get("/products")["data"]
                               if args.product_id is None or p["id"] == args.product_id]}
        elif args.command == "orders":
            if args.per_page > 100:
                raise ApiError("--per-page must be at most 100")
            params = {"product_id": args.product_id, "page": args.page, "per_page": args.per_page,
                      "status": args.status, "location_id": args.location_id}
            response = client.get("/orders", params)
            result = {"data": [order_summary(o) for o in response["data"]],
                      "meta": select(response.get("meta", {}), ("current_page", "last_page", "per_page", "total"))}
        elif args.command == "order":
            result = order_summary(client.get(f"/orders/{args.order_id}"))
        else:
            result = purchase(client, args)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ApiError, OSError, KeyError, TypeError, ValueError) as exc:
        # Only our deliberately authored errors may contain text. Never print raw API data.
        message = str(exc) if isinstance(exc, ApiError) else "Unexpected API schema or local file error; no raw data printed"
        print(json.dumps({"error": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
