---
name: iproyal-ops
description: Operate IPRoyal through its dashboard API. Inspect balances, products, proxy orders, IPs and expiry; quote and explicitly purchase new ISP or datacenter proxy orders. Use for IPRoyal account operations, not AdsPower profile setup or unrelated deployment changes.
---

# IPRoyal Ops

Use the official reseller API at `https://apid.iproyal.com/v1/reseller` with an
organization/dashboard API token in `X-Access-Token`. The legacy API is retired.

## Credentials and output

- Token precedence: `IPROYAL_API_TOKEN`, `IPROYAL_TOKEN_FILE`, then
  `~/.config/iproyal/token`. Files must be owned by the current user and mode 0600;
  keep the containing directory private. Do not pass tokens as CLI arguments.
- Resolve the helper relative to this file: `scripts/iproyal.py` (Python 3.10+ and curl).
- Order responses contain proxy usernames/passwords, even when listing expired orders.
  The helper prints only allowlisted metadata and IPs. Do not dump raw API responses.
- When explicitly authorized to inject proxy credentials, import `Client` into an
  in-memory operation and pipe the needed fields directly to the approved destination.
  Do not add a raw/reveal flag or persist a response file in a workspace.

## Read and quote

```bash
python3 scripts/iproyal.py balance
python3 scripts/iproyal.py products
python3 scripts/iproyal.py products --product-id 9 --location-search Singapore
python3 scripts/iproyal.py orders --product-id 9 --status confirmed
python3 scripts/iproyal.py order ORDER_ID
```

Use returned product/plan/location IDs, not historical examples. Product and location
names may be localized; the products search also checks child locations. Orders are
paged; `meta.last_page` indicates more results. Inspect `expire_date` directly; the
documented expiring-soon filter returned unfiltered orders in live validation and is
not exposed by this helper. The current API requires `product_id`
for listing orders. Order expiry timestamps have no offset; report them as provider
timestamps unless the provider confirms a timezone.

```bash
python3 scripts/iproyal.py quote --product-id PRODUCT_ID --plan-id PLAN_ID \
  --location-id LOCATION_ID --quantity 1
python3 scripts/iproyal.py create-order --product-id PRODUCT_ID --plan-id PLAN_ID \
  --location-id LOCATION_ID --quantity 1
```

`quote` and `create-order` without `--execute` perform GETs only. They fetch current
catalog, validate plan/location/quantity and required answers, calculate pricing,
and show the balance and exact purchase parameters. Use `--answers-file` for a
non-secret JSON question-ID-to-answer map, including device-count options if needed.
For schema/endpoint details read [references/api.md](references/api.md).

## Purchase

Creating this skill, inspecting an order, or possessing a token is not permission to
spend. Confirm the user's chosen product, location, quantity, duration, maximum total,
and renewal policy before sending a purchase. Existing explicit authorization for
those exact parameters is sufficient; do not ask again solely because a skill is used.

```bash
python3 scripts/iproyal.py create-order --product-id PRODUCT_ID --plan-id PLAN_ID \
  --location-id LOCATION_ID --quantity 1 --execute --max-total APPROVED_TOTAL
```

The helper purchases from balance only and defaults `auto_extend=false`. Use
`--auto-extend` only with authorization for recurring balance-funded renewal.
It requotes immediately before POST and rejects a price above `--max-total` or balance.
It never retries a POST. A timeout/server error may mean the order was created:
inspect orders/balance and reconcile before another purchase, never blindly retry.
After success, read the exact returned order ID and confirm fulfillment/IP assignment.
Do not claim a quote is a completed order or that a new purchase retains an expired IP.

## Operational checks

- Distinguish expired/reclaimed IPs from credential drift and source/target restrictions.
- Check auto-renewal status and balance when investigating expiry; do not enable it silently.
- Catalog questions can offer access from 3/5/10 devices. Inspect the actual order/option;
  do not infer a device limit solely from a 403 or silently pay for an upgrade.
- A general KYC banner does not establish why a particular request failed. Respect provider
  restrictions; do not bypass them. Compare authenticated local and deployed probes.
- Verify deployed egress IP/country and real API requests after an authorized rotation;
  successful proxy CONNECT or application /health alone is insufficient.
- Renewal, credential reset, auto-renewal changes and source allowlisting are separate
  mutations; read the API reference and honor the user's scope. They are not generic CLI modes.
