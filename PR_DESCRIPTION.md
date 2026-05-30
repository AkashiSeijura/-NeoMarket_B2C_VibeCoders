## US-ORD-05

Implemented final reserve fulfillment when an order transitions `DELIVERING -> DELIVERED`. Because this repo is FastAPI/SQLAlchemy rather than Django, the trigger is a service-level admin action (`transition_order_status`) exposed through a hidden service-key route; it commits `DELIVERED` before calling B2B so a fulfill failure never rolls the order back. B2C calls the published B2B OpenAPI path `POST /api/v1/inventory/fulfill` and falls back to the legacy flow path `POST /api/v1/fulfill`; retry scaffold `retry_delivered_fulfillments` replays `DELIVERED` orders and relies on B2B order_id idempotency.

Contract check: published B2C OpenAPI has no dedicated fulfill endpoint, but includes `DELIVERED` in `OrderResponse.status`; canonical flow `b2c-orders-flows.md#b2c-13-fulfill` defines the transition side effect and retry rule. Published B2B OpenAPI defines fulfill as `/api/v1/inventory/fulfill` with `{order_id, items}` and `FULFILLED` response, so B2C targets that first.

## ADR: delivered fulfill trigger

I considered a Django `post_save` signal, a Django Admin action, and overriding model `save()`. This service is not Django, so I chose the closest equivalent to an Admin action: an explicit service function for status transitions, callable from a hidden internal route and directly from tests. Compared with a signal or `save()` override, the explicit action has lower risk of accidental double calls on unrelated persistence and is easy to test without Django Admin. Repeated `DELIVERED` calls are still tolerated because B2B owns idempotency by `order_id`.

## Test evidence: US-ORD-05

`python -m pytest tests/api/test_orders.py -q -k "delivered_status_triggers_fulfill_to_b2b or fulfill_failure_retried_asynchronously or repeated_fulfill_idempotent"`

- `test_delivered_status_triggers_fulfill_to_b2b`: passed
- `test_fulfill_failure_retried_asynchronously`: passed
- `test_repeated_fulfill_idempotent`: passed
- full B2C suite: passed with `python -m pytest -q`

## US-ORD-04

Implemented incoming B2B product events. The service accepts flow-compatible `POST /api/v1/events/product` and published OpenAPI `POST /api/v1/b2b/events`, checks `X-Service-Key`, stores event idempotency keys, and batch-updates matching `cart_items.unavailable_reason` to `PRODUCT_BLOCKED`, `PRODUCT_DELETED`, or `OUT_OF_STOCK`. Orders and `order_items` are not changed.

Contract check: `flows/b2c-orders-flows.md#b2c-12-handle-events` defines `/api/v1/events/product` with `event`, `sku_ids`, and `date`; published B2C OpenAPI defines `/api/v1/b2b/events` with `event_type`, `occurred_at`, and `payload`. Because OpenAPI has priority on conflicts but the executable flow requires `/events/product`, the implementation supports both formats through one handler.

## ADR: event idempotency

I considered a separate `EventIdempotencyKey` table, storing the last event key on `cart_items`, and Redis with TTL. I chose a separate DB table because it is durable, simple to query before applying side effects, and avoids coupling idempotency to rows that may not exist for every affected buyer. A `cart_items` field would miss events when no cart row exists yet and cannot represent one event affecting many rows cleanly. Redis with TTL is fast and self-cleaning, but risks losing idempotency on cache flush/restart; with the table, disk growth is the main tradeoff and old keys can be cleaned by age with a simple scheduled delete.

## Test evidence: US-ORD-04

`python -m pytest -q`

- `test_product_blocked_marks_cart_items_unavailable`: passed
- `test_orders_not_affected_by_product_blocked`: passed
- `test_idempotent_event_no_side_effects`: passed
- `test_missing_service_key_returns_401`: passed
- `test_openapi_b2b_events_endpoint_accepts_product_event`: passed
- full B2C suite: 70 passed

## US-ORD-02

Implemented `GET /api/v1/orders` with `limit`, `offset`, and `status` filtering, plus `GET /api/v1/orders/{order_id}`. Buyer identity for order endpoints now comes only from Bearer JWT `sub`; `X-User-Id` is not accepted for orders. Order detail uses persisted `OrderItem.unit_price`, `product_title`, and `sku_name`, so later B2B SKU price changes do not affect historical orders. Contract check: published B2C OpenAPI defines `GET /api/v1/orders` as `PaginatedOrders` with `OrderResponse` items, while the flow shows a compact list with `items_count`; implementation follows OpenAPI priority.

## ADR: order IDOR protection

I considered `filter(buyer_id=request.user).get(id=...)`, loading by `id` first and checking owner separately, and moving ownership into a reusable permission/dependency layer. I chose the scoped query (`WHERE id = :id AND buyer_id = jwt.sub`) because it is readable at the service boundary and naturally returns the same `ORDER_NOT_FOUND` for missing and foreign orders. Loading first then checking owner makes it easier to accidentally return 403 or leak existence through logging/branching. A permission class could reduce repetition later, but this service has only a few order endpoints and the scoped query keeps the unexpected absence behavior explicit.

## Test evidence: US-ORD-02

`python -m pytest -q`

- `test_orders_list_returns_own_orders_paginated`: passed
- `test_order_detail_shows_fixed_prices`: passed
- `test_other_user_order_returns_404_not_403`: passed
- full B2C suite: 65 passed

## US-CART-02

Implemented product subscriptions on `POST /api/v1/favorites/{product_id}/subscribe` and `DELETE /api/v1/favorites/{product_id}/subscribe`. The buyer id is taken only from Bearer JWT `sub`; query/body user ids are not accepted. The endpoint validates `notify_on`, verifies the product through B2B before saving, returns `201` with `notify_on` on success, `409 DUPLICATE_SUBSCRIPTION` for the same buyer/product, `400 INVALID_NOTIFY_ON` for empty or unsupported events, and `404` for unknown products. Published B2C OpenAPI currently exposes the same route with request field `events` and `204`; the implementation accepts `events` as a compatibility alias but returns the flow/DoD response shape with `notify_on`.

## ADR: product subscription storage

I considered PostgreSQL `ArrayField`, a separate subscription-event table, and a JSON field on the subscription row. I chose a JSON `notify_on` field because it is portable across the current SQLite test setup and the service database, and adding a new notification type does not require a schema migration. A separate event table would make filtering by event type simpler and more index-friendly, but it adds joins and extra write paths before notification dispatch exists. `ArrayField` is compact and filterable in PostgreSQL, but ties the model to one database backend and complicates local tests.

## Test evidence: US-CART-02

`python -m pytest -q`

- `test_subscribe_returns_201_with_notify_on`: passed
- `test_duplicate_subscription_returns_409`: passed
- `test_invalid_notify_on_returns_400`: passed
- `test_subscribe_to_unknown_product_returns_404`: passed
- `test_unsubscribe_returns_204`: passed
- full B2C suite: 53 passed

## US-CART-03

Implemented B2C cart storage for guest (`X-Session-Id`) and authorized users (`Authorization: Bearer <JWT>` with `sub`, plus `X-User-Id` gateway fallback). Cart CRUD enriches every read from B2B and never stores price, stock, or `unavailable_reason`. Guest merge uses `MAX(guest.quantity, auth.quantity)` on SKU conflicts.

Contract check: implementation was reconciled with `flows/b2c-cart-flows.md#b2c-8-cart` and the published B2C OpenAPI `bundled/b2c.yaml`. Cart responses now include OpenAPI fields (`items_count`, `subtotal`, `is_valid`), keep flow extensions (`summary`, `checkout_payload`, `unavailable_reason`), and expose OpenAPI routes `PATCH /api/v1/cart/items/{sku_id}`, `DELETE /api/v1/cart/items/{sku_id}`, `POST /api/v1/cart/validate`, and `POST /api/v1/cart/merge`.

## ADR

Guest cart identity options considered: `X-Session-Id`, cookie, and temporary JWT. I chose `X-Session-Id`: it is explicit in the canonical flow, works the same for mobile and web clients, and does not depend on browser cookie behavior. A cookie is convenient for browsers but weaker for mobile clients and cross-domain setups. A temporary JWT reduces identifier spoofing risk, but needs token issuing/rotation infrastructure that this service does not own yet; for now the session id must be opaque UUID generated by the client or gateway.

## Test evidence

`python -m pytest -q`

- `test_add_sku_increments_quantity_if_already_in_cart`: passed
- `test_get_cart_enriched_with_b2b_data`: passed
- `test_unavailable_sku_shown_with_reason`: passed
- `test_guest_cart_merged_on_login`: passed
- `test_cart_openapi_patch_delete_and_validate_by_sku`: passed
- `test_subtotal_excludes_unavailable_lines`: passed
- `test_merge_requires_session_header`: passed
- `test_cart_validate_returns_issues`: passed

## US-CAT-01

Implemented catalog proxy endpoints `GET /api/v1/catalog/products` and flow-compatible `GET /api/v1/products`, plus `GET /api/v1/catalog/facets`. The product endpoint accepts OpenAPI `q`, `sort`, `filter[...]` and flow-compatible `category_id` / `filters[...]`, clamps pagination to `1..100`, validates sort against the published B2C enum (`price_asc`, `price_desc`, `popularity`, `new`), and forwards requests to B2B with `X-Service-Key`. Responses are normalized to the canon/OpenAPI card shape: `name`, `images`, `min_price`, `has_stock`, and `{items,total_count,limit,offset}`.

## ADR: facets

Considered three options for facets: SQL `GROUP BY` on each request in B2B, cached facets with TTL, and denormalized counters in a separate table. I chose request-time calculation/proxy for MVP, with B2B as the source of truth and a B2C no-storage fallback only when the facets endpoint is not published yet. This keeps data consistency high because visibility (`MODERATED`, not deleted, positive active quantity) remains owned by B2B. The tradeoff is higher DB load for large catalogs, so TTL cache is the next step once traffic or category size justifies it.

## Test evidence: US-CAT-01

`python -m pytest -q`

- `test_catalog_returns_filtered_sorted_products`: passed
- `test_facets_return_counts_per_filter_value`: passed
- `test_invalid_sort_returns_400`: passed
- `test_b2b_unavailable_returns_502`: passed
- `test_catalog_b2b_client_uses_service_key`: passed

## US-CAT-03

Implemented B2C product card endpoints `GET /api/v1/catalog/products/{product_id}` and flow-compatible `GET /api/v1/products/{product_id}`. The service requests the product from B2B, rejects hidden products with 404, normalizes images/attributes/SKU prices to the published B2C OpenAPI shape, and keeps out-of-stock SKU in the response with `available_quantity=0`. Seller-only SKU fields `cost_price` and `reserved_quantity` are not present in the response.

## ADR: product card representation

I considered three options: separate B2C serializer/normalizer, view-level field filtering, and a fully separate internal endpoint. I chose a separate B2C normalizer because it has the lowest accidental leak risk when B2B adds seller-only fields to its model or response. View-level filtering is shorter, but fragile: a new nested field can bypass the filter unless every path is audited. A separate endpoint would also be safe, but increases B2B/B2C contract surface and support cost; the normalizer keeps one integration point and an explicit allow-list for buyer-visible fields.

## Test evidence: US-CAT-03

`python -m pytest -q`

- `test_product_card_returns_full_data_with_skus`: passed
- `test_cost_price_absent_in_response`: passed
- `test_blocked_product_returns_404`: passed
- `test_sku_without_stock_is_shown_as_unavailable`: passed

## US-ORD-01

Implemented `POST /api/v1/orders` checkout with idempotency, all-or-nothing B2B reserve, and historical `OrderItem` snapshots (`unit_price`, `product_title`, `sku_name`). The route follows the published B2C OpenAPI by accepting `Idempotency-Key` header and also accepts the canonical flow body fields (`idempotency_key`, `items`, `delivery_address`) for compatibility. Successful checkout creates a `PAID` order; reserve failures return `409 RESERVE_FAILED` with `failed_items`; B2B downtime returns `503 B2B_UNAVAILABLE`.

## ADR: checkout idempotency

I considered three storage options: a unique index on `orders.idempotency_key`, a separate idempotency-key table/cache, and Redis. I chose the unique DB index on `orders.idempotency_key` plus a stored request hash because it is the simplest durable option in this service and handles duplicate inserts under race conditions at the database boundary. Redis is fast but adds operational state and persistence questions; a separate table is more flexible for pending/in-progress states, but adds extra write paths that are not needed for this MVP. B2B reserve is called with the same idempotency key, so concurrent duplicate checkout attempts do not create duplicate orders and should not double-reserve on the B2B side.

## Test evidence: US-ORD-01

`python -m pytest -q`

- `test_checkout_creates_paid_order_with_fixed_prices`: passed
- `test_partial_reserve_failure_returns_409`: passed
- `test_idempotency_returns_existing_order`: passed
- `test_b2b_unavailable_returns_503`: passed

## US-ORD-03

Implemented `POST /api/v1/orders/{order_id}/cancel`. The route checks ownership through the authenticated buyer, returns `404 ORDER_NOT_FOUND` for another user's order, allows cancellation only from `CREATED` and `PAID`, calls B2B `POST /api/v1/unreserve`, and moves the order to `CANCELLED` on success or `CANCEL_PENDING` when B2B unreserve is unavailable.

Contract check: flow `b2c-orders-flows.md#b2c-11-cancel-order` requires `CREATED/PAID -> CANCELLED` on successful unreserve and `CREATED/PAID -> CANCEL_PENDING` on timeout/5xx. Published B2C OpenAPI contains `POST /api/v1/orders/{order_id}/cancel`, returns `OrderResponse`, includes `CANCEL_PENDING` in the order status enum, and defines `409` for disallowed status. Its prose also mentions `ASSEMBLING` as cancellable, but the canonical flow and task DoD require `ASSEMBLING -> 409 CANCEL_NOT_ALLOWED`, so the implementation follows the executable acceptance criteria.

## ADR: cancel retry

I considered three retry options: Celery task with exponential backoff, a management command run by cron, and Django Q. I chose a DB-backed service scaffold (`retry_pending_cancellations`) that can be wired to cron first, because it has the lowest environment setup cost and survives service restarts through persisted `CANCEL_PENDING` rows. Celery gives stronger scheduling/backoff semantics, but requires broker/runtime setup that this repo does not have yet. Django Q has similar operational overhead and is less aligned with the current FastAPI/SQLAlchemy stack.

## Test evidence: US-ORD-03

`python -m pytest -q`

- `test_cancel_paid_order_transitions_to_cancelled`: passed
- `test_unreserve_failure_transitions_to_cancel_pending`: passed
- `test_cancel_assembling_order_returns_409`: passed
- `test_other_user_order_returns_404`: passed

## US-CAT-02

Implemented B2C text search for the flow-compatible `GET /api/v1/products?search=...` alias while keeping the published OpenAPI `GET /api/v1/catalog/products?q=...` behavior. B2C validates search length (`3..255`) with canonical `400 INVALID_REQUEST`, trims the query, forwards `search` to B2B for the flow alias, and keeps category/filter/sort/pagination compatibility from US-CAT-01. Empty results return the normal paginated 200 response.

## ADR: product search

I considered SQL `LIKE`/`icontains`, `pg_trgm`, and full-text `SearchVector`. I chose escaped SQL `LIKE`/`icontains` for MVP because it has the lowest implementation complexity and works in the existing B2B database/query layer without new indexes or PostgreSQL extensions. `pg_trgm` would improve fuzzy relevance later, while `SearchVector` is better for ranking and language-aware search but is heavier than this flow requires. Relevance is intentionally basic: match `title` or `description`, then keep existing catalog sorting.

## Test evidence: US-CAT-02

`python -m pytest -q`

- `test_search_returns_matching_products`: passed
- `test_short_query_returns_400`: passed
- `test_special_chars_do_not_break_query`: passed
- `test_empty_results_returns_200`: passed
- full B2C suite: 30 passed

## US-CAT-04

Implemented similar products for `GET /api/v1/catalog/products/{product_id}/similar` and the flow-compatible alias `GET /api/v1/products/{product_id}/similar`. The endpoint verifies the current product through B2B, returns `404 NOT_FOUND` for unknown/hidden products, fetches alternatives from the same category, excludes the current product, and fills from the parent category when B2B returns fewer than requested. The response follows the published B2C OpenAPI for this endpoint: an array of `CatalogProductCard`; default limit is 8 for the canonical flow/DoD, while query validation allows the OpenAPI limit range up to 50.

## ADR: similar product selection

I considered three approaches: random category selection (`ORDER BY RANDOM()`), ranking by maximum attribute overlap, and cached precomputed recommendations. I chose category-based selection proxied to B2B with parent-category fallback for MVP because it has the lowest implementation complexity and keeps visibility/category consistency in the product source of truth. Attribute matching would be more relevant but requires a stable characteristic taxonomy and scoring rules that are not present yet. Cached recommendations would make repeated requests very stable and fast, but add invalidation complexity; for now consistency with current B2B product state is more important than cache speed.

## Test evidence: US-CAT-04

`python -m pytest -q`

- `test_similar_returns_up_to_8_from_same_category`: passed
- `test_empty_category_returns_200_empty_list`: passed
- `test_unknown_product_returns_404`: passed
- `test_similar_fallback_uses_parent_category`: passed
- full B2C suite: 34 passed

## US-CAT-05

Implemented category navigation endpoints: published OpenAPI routes `GET /api/v1/catalog/categories`, `GET /api/v1/catalog/categories/tree`, `GET /api/v1/catalog/categories/{category_id}`, plus flow-compatible `GET /api/v1/categories`, `GET /api/v1/categories/{category_id}`, and `GET /api/v1/breadcrumbs`. B2C builds a nested tree and breadcrumbs from the flat B2B category list, returns `404 NOT_FOUND` for unknown categories, `422 orphan_node` for broken hierarchy, and `400 ambiguous_param` when breadcrumbs receives both `category_id` and `product_id`. The OpenAPI tree route returns an array as published; the flow alias wraps it as `{items}`.

## ADR: category hierarchy

I considered PostgreSQL `ltree`, adjacency list with recursive queries, and materialized path. I chose adjacency list for MVP because B2B already provides `parent_id`, and B2C can detect orphan nodes by checking every non-null parent against the flat index in O(n). Breadcrumbs are slower than materialized path because they walk parent links, but category depth is small and category data is seed-like/cacheable. `ltree` and materialized path would make breadcrumbs faster, but they require storage/indexing ownership in B2B and more careful updates when moving a subtree.

## Test evidence: US-CAT-05

`python -m pytest -q`

- `test_category_tree_returns_nested_structure`: passed
- `test_breadcrumbs_return_path_from_root`: passed
- `test_unknown_category_returns_404`: passed
- `test_ambiguous_params_returns_400`: passed
- `test_missing_breadcrumb_param_returns_400`: passed
- `test_orphan_node_returns_422`: passed
- full B2C suite: 43 passed

## US-CART-01

Implemented buyer favorites storage with `user_id` taken only from Bearer JWT `sub`: `GET /api/v1/favorites`, OpenAPI-compatible `PUT /api/v1/favorites/{product_id}`, flow-compatible `POST /api/v1/favorites/{product_id}`, and idempotent `DELETE /api/v1/favorites/{product_id}`. Favorites store only `user_id`, `product_id`, and `added_at`; reads enrich product cards from B2B by batch `ids` and exclude products that B2B does not return as public/visible. Query/body `user_id` is not declared on the endpoints and is ignored by FastAPI, so cross-user reads use the JWT identity.

Published B2C OpenAPI currently defines `GET`, `PUT`, and `DELETE` for favorites, with `PUT` returning `204`; the canonical flow/DoD also requires `POST` returning `201` for first add and `200` for repeat add. The implementation supports both: `PUT` is kept for OpenAPI compatibility, while `POST` is added as a hidden flow-compatible route for acceptance tests.

## ADR: favorite user identity

I considered three identity options: `user_id` from query, `user_id` from JWT claims, and `X-User-Id`. Query `user_id` is rejected because it creates a direct IDOR risk: a client can ask for another buyer's list. `X-User-Id` is simple, but spoofable without a trusted gateway boundary. I chose Bearer JWT `sub` because it has the best IDOR protection with low implementation complexity in this FastAPI service.

## Test evidence: US-CART-01

`python -m pytest tests/api/test_favorites.py -q`

- `test_add_to_favorites_returns_201`: passed
- `test_get_favorites_enriched_from_b2b`: passed
- `test_repeat_add_returns_200_not_duplicate`: passed
- `test_blocked_product_excluded_from_list`: passed
- `test_user_id_from_query_is_ignored`: passed
- full B2C suite: 48 passed

## US-CART-04

Implemented home page banners with flow-compatible `GET /api/v1/home/banners`, OpenAPI-compatible `GET /api/v1/catalog/banners`, and public `POST /api/v1/banner-events` for batched `impression`/`click` CTR events. Active banners are filtered by `is_active`, `start_at`, `end_at`, sorted by ascending `priority`, and returned as an empty 200 slider when nothing is active. Unknown banner events return `400 BANNER_NOT_FOUND`; empty event batches return `400 EMPTY_EVENTS`.

Published B2C OpenAPI exposes banners as `GET /api/v1/catalog/banners` returning an array with `ordering/active_from/active_to`; the canonical flow requires `GET /api/v1/home/banners` returning `{items,total_count}` with `priority`. The implementation supports both shapes: `/catalog/banners` follows OpenAPI, `/home/banners` follows the executable flow and DoD. Published B2C OpenAPI does not currently describe `POST /api/v1/banner-events`, so this service exposes it in its generated schema with the flow request/response shape.

## ADR: banner click analytics

I considered three storage options for CTR analytics: writing every event to a relational table, buffered batch writes, and sending events to an external analytics system. I chose relational row-per-event storage for this MVP because it is the simplest to operate in the current service and makes CTR aggregation straightforward with SQL over `banner_events`. The downside is higher DB write load on a high-traffic homepage, so buffered writes or an external analytics pipeline would be a better next step when traffic grows. For now the main criteria are low implementation complexity and simple aggregation by `banner_id/event`.

## Test evidence: US-CART-04

`python -m pytest -q`

- `test_active_banners_returned_sorted_by_priority`: passed
- `test_no_active_banners_returns_200_empty`: passed
- `test_click_on_unknown_banner_returns_400`: passed
- full B2C suite: 58 passed
