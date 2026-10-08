# Official API contract

Based on official documentation and read-only API validation.

- [API/authentication](https://docs.iproyal.com/proxies/isp/api)
- [Products, plans, locations, questions](https://docs.iproyal.com/proxies/isp/api/products)
- [Order list/detail, pricing, create, extend, auto-extend](https://docs.iproyal.com/proxies/isp/api/orders)
- [Balance](https://docs.iproyal.com/proxies/isp/api/user)
- [Proxy availability and credential changes](https://docs.iproyal.com/proxies/isp/api/proxies)

Base: `https://apid.iproyal.com/v1/reseller`; header `X-Access-Token`.
Use `.md` suffix for the text version of official docs. Do not use the deprecated
legacy/Postman API. Requests are JSON; pricing parameters are URL query fields.

| Endpoint | Method | Purpose |
| --- | --- | --- |
| /balance | GET | Numeric account balance |
| /products | GET | data array: IDs, plans, locations with nested child_locations, questions |
| /orders | GET | product_id required in practice, page/per_page, optional status/location_id/status_is_expiring_soon |
| /orders/{id} | GET | One order, includes credential-bearing proxy_data |
| /orders/calculate-pricing | GET | product_id, product_plan_id, product_location_id, quantity, optional coupon/answers |
| /orders | POST | Purchase; same IDs/quantity, product_question_answers, auto_extend; no card_id means balance |
| /orders/{id}/extend | POST | product_plan_id; optional proxies; omitted/empty proxies extends ALL IPs |
| /orders/toggle-auto-extend | POST | order_id, is_enabled, optional plan, payment_type and card_id |

The helper deliberately supports one location per purchase and no card charges.
The API also supports selection.locations for bulk/multiple locations; not exposed by
this helper. Use a separately reviewed payload if the user explicitly needs that scope.

`price_with_vat` is the total used for the purchase ceiling. Treat price changes,
missing/malformed totals, unrecognized plans/locations, sold-out locations, and balance
shortfalls as preflight failures. Quotes do not reserve stock or guarantee server-side
price locking; the documented purchase endpoint has no maximum-price or idempotency key.

Order metadata includes `id`, `status`, `expire_date`, `plan_name`, `location`, `quantity`,
`auto_extend_settings`. `proxy_data.ports` maps `http|https` and `socks5` to ports;
`proxy_data.proxies` contains objects with `ip`, `username`, `password`.
Never print those objects wholesale. Free-form notes/question answers can also hold secrets.

Order statuses: unpaid, in-progress, confirmed, refunded, expired. Confirmed plus assigned
IPs is fulfillment evidence; it does not prove runtime connectivity.
The documented `status_is_expiring_soon` filter returned both expired and future orders
in live validation; do not rely on it for expiry alerts without revalidating behavior.

The proxy availability endpoint requires provider enablement and a documented minimum
total spend of $10,000. Ordinary product/location stock inspection does not require it.
Do not spend or change account access to unlock that endpoint during routine validation.

Live catalog IDs are examples, not defaults: ISP product 9, 30-day plan 22, Singapore parent
location 27 / available city 1124. Labels can be Chinese. Always refresh before ordering.
