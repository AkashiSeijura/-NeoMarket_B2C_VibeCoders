# NeoMarket B2C

FastAPI service scaffold for B2C flows.

Implemented:

- `GET /api/v1/cart`
- `DELETE /api/v1/cart`
- `POST /api/v1/cart/items`
- `GET /api/v1/cart/items/{item_id}`
- `PUT /api/v1/cart/items/{item_id}`
- `DELETE /api/v1/cart/items/{item_id}`
- `POST /api/v1/cart/merge`

Cart stores owner identity, `sku_id`, `product_id`, and `quantity`.
Prices, stock, availability, and `unavailable_reason` are calculated from B2B on read.
Adding to cart does not reserve stock.

Run:

```bash
python -m pytest
uvicorn src.main:app --reload
```

