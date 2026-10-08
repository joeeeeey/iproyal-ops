# IPRoyal Ops

[![skills.sh](https://skills.sh/b/joeeeeey/iproyal-ops)](https://skills.sh/joeeeeey/iproyal-ops/iproyal-ops)

An agent skill and Python CLI for inspecting IPRoyal proxy orders and preparing
explicit, balance-funded purchases through the official dashboard API.

## Features

- Query balance, products, plans, locations and stock.
- List orders with product, status and location filters, or inspect a specific order.
- Show proxy IPs, expiration dates and auto-renewal status without printing credentials.
- Preview a purchase with a fresh quote, catalog validation and balance check.
- Create an order only with an explicit execution flag and spending ceiling.

Existing-order renewal, credential resets, whitelist changes, account top-ups and
deployment updates are not implemented as CLI commands. No live purchase is needed
to run the tests.

## Requirements and installation

Python 3.10+ and `curl` on macOS or Linux. No third-party Python dependencies.

Install with the official [skills CLI](https://skills.sh/docs/cli) (requires Node.js/npm):

```sh
npx skills add joeeeeey/iproyal-ops --skill iproyal-ops
```

To select Codex or Claude Code explicitly:

```sh
npx skills add joeeeeey/iproyal-ops --skill iproyal-ops --agent codex
npx skills add joeeeeey/iproyal-ops --skill iproyal-ops --agent claude-code
```

Installation is project-local by default; add `--global` for your user account.
The CLI's default anonymous installation telemetry powers skills.sh discovery.
Set `DISABLE_TELEMETRY=1` to opt out. Installing the skill does not configure an
IPRoyal token, query your account, or purchase proxies.

For standalone CLI use or manual skill installation:

```sh
git clone https://github.com/joeeeeey/iproyal-ops.git
cd iproyal-ops
python3 scripts/iproyal.py --help
```

For Codex, link the repository into your skills directory, provided that name is
not already installed:

```sh
mkdir -p "$HOME/.codex/skills"
ln -s "$PWD" "$HOME/.codex/skills/iproyal-ops"
```

Other agents that support `SKILL.md` can load the skill from this repository.

## Authentication

Get an organization/dashboard API token from [IPRoyal](https://dashboard.iproyal.com/).
The CLI checks, in order:

1. `IPROYAL_API_TOKEN` environment variable.
2. File referenced by `IPROYAL_TOKEN_FILE`.
3. `~/.config/iproyal/token`.

Store the token outside this repository using your secret manager or a private file
owned by your user with mode `0600`, under a private directory. Never paste a token
into a command argument, commit it, or save raw order API responses: order responses
contain proxy passwords. The CLI sends the token through curl's stdin and prints
allowlisted order metadata only.

## Inspect orders

```sh
python3 scripts/iproyal.py balance
python3 scripts/iproyal.py products
python3 scripts/iproyal.py products --product-id 9 --location-search Singapore
python3 scripts/iproyal.py orders --product-id 9 --status confirmed
python3 scripts/iproyal.py orders --product-id 9 --page 2 --per-page 20
python3 scripts/iproyal.py order ORDER_ID
```

Discover current IDs through `products`; example IDs are not guaranteed to remain
valid. Names may be localized. Inspect `meta.last_page` when listing orders.
Expiration timestamps are shown as supplied by IPRoyal, without assuming a timezone.

## Quote and purchase

Replace uppercase placeholders with IDs from the current catalog:

```sh
python3 scripts/iproyal.py quote \
  --product-id PRODUCT_ID --plan-id PLAN_ID \
  --location-id LOCATION_ID --quantity 1

# Preview only: performs GET requests and does not purchase.
python3 scripts/iproyal.py create-order \
  --product-id PRODUCT_ID --plan-id PLAN_ID \
  --location-id LOCATION_ID --quantity 1

# Purchase only after approving the exact parameters and maximum total.
python3 scripts/iproyal.py create-order \
  --product-id PRODUCT_ID --plan-id PLAN_ID \
  --location-id LOCATION_ID --quantity 1 \
  --execute --max-total APPROVED_TOTAL
```

Purchases use account balance, not a credit card. Auto-renewal defaults to disabled;
`--auto-extend` enables recurring balance-funded renewal and needs explicit approval.
`--coupon` and a non-secret question-ID-to-answer JSON `--answers-file` are supported.

The CLI requotes before purchasing and rejects totals above the approved ceiling or
available balance. The API does not document a server-side price lock; the ceiling is
a client-side preflight check. Stock and pricing may change between quote and purchase.

POST requests are never automatically retried. If a purchase times out, inspect orders
and balance before retrying to avoid duplicate charges. Confirm the returned order's
status and assigned IPs before configuring a consumer.

## Tests

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

The tests run offline and cover preview behavior, price and balance guards, redaction,
catalog validation and non-retry of purchases. Read-only operations and quoting have
also been checked against the live API; real spending is intentionally excluded from
automated validation.

See [SKILL.md](SKILL.md) for agent instructions and [API notes](references/api.md)
for endpoint details and known limitations.
