class ServiceError(Exception):
    status_code = 400
    code = "INVALID_REQUEST"

    def __init__(self, message: str | None = None):
        self.message = message or self.code
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


class MissingCartIdentityError(ServiceError):
    status_code = 400
    code = "MISSING_CART_IDENTITY"


class UnauthorizedError(ServiceError):
    status_code = 401
    code = "UNAUTHORIZED"


class NotFoundError(ServiceError):
    status_code = 404
    code = "NOT_FOUND"


class OrderNotFoundError(NotFoundError):
    code = "ORDER_NOT_FOUND"


class CartItemNotFoundError(NotFoundError):
    code = "CART_ITEM_NOT_FOUND"


class SkuNotFoundError(NotFoundError):
    code = "SKU_NOT_FOUND"


class SkuNotAvailableError(ServiceError):
    status_code = 404
    code = "SKU_NOT_AVAILABLE"


class InsufficientStockError(ServiceError):
    status_code = 409
    code = "INSUFFICIENT_STOCK"


class InvalidQuantityError(ServiceError):
    status_code = 400
    code = "INVALID_QUANTITY"


class InvalidNotifyOnError(ServiceError):
    status_code = 400
    code = "INVALID_NOTIFY_ON"


class DuplicateSubscriptionError(ServiceError):
    status_code = 409
    code = "DUPLICATE_SUBSCRIPTION"


class BannerNotFoundError(ServiceError):
    status_code = 400
    code = "BANNER_NOT_FOUND"


class EmptyEventsError(ServiceError):
    status_code = 400
    code = "EMPTY_EVENTS"


class InvalidSortError(ServiceError):
    status_code = 400
    code = "INVALID_SORT"


class InvalidSearchQueryError(ServiceError):
    status_code = 400
    code = "INVALID_REQUEST"


class BreadcrumbParamError(ServiceError):
    status_code = 400

    def __init__(self, error: str, message: str):
        self.error = error
        super().__init__(message)

    def to_dict(self) -> dict:
        return {"error": self.error, "message": self.message}


class CategoryHierarchyError(ServiceError):
    status_code = 422

    def __init__(self):
        self.error = "orphan_node"
        super().__init__("category hierarchy is broken")

    def to_dict(self) -> dict:
        return {"error": self.error, "message": self.message}


class B2BUnavailableError(ServiceError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"


class B2BCheckoutUnavailableError(B2BUnavailableError):
    code = "B2B_UNAVAILABLE"


class B2BRequestError(ServiceError):
    code = "B2B_ERROR"

    def __init__(self, status_code: int, message: str | None = None, code: str | None = None):
        self.status_code = status_code
        self.code = code or self.code
        super().__init__(message)


class IdempotencyConflictError(ServiceError):
    status_code = 409
    code = "IDEMPOTENCY_CONFLICT"


class EmptyOrderError(ServiceError):
    status_code = 400
    code = "INVALID_REQUEST"


class ReserveFailedError(ServiceError):
    status_code = 409
    code = "RESERVE_FAILED"

    def __init__(self, message: str | None = None, failed_items: list[dict] | None = None):
        self.failed_items = failed_items or []
        super().__init__(message or "Failed to reserve order items")

    def to_dict(self) -> dict:
        return {**super().to_dict(), "failed_items": self.failed_items}


class CancelNotAllowedError(ServiceError):
    status_code = 409
    code = "CANCEL_NOT_ALLOWED"

    def __init__(self, current_status: str):
        self.current_status = current_status
        super().__init__(f"Cancellation is not allowed for order in status {current_status}")

    def to_dict(self) -> dict:
        return {**super().to_dict(), "current_status": self.current_status}
