class ServiceError(Exception):
    status_code = 400
    code = "INVALID_REQUEST"

    def __init__(self, message: str | None = None):
        self.message = message or self.code
        super().__init__(self.message)


class MissingCartIdentityError(ServiceError):
    status_code = 400
    code = "MISSING_CART_IDENTITY"


class UnauthorizedError(ServiceError):
    status_code = 401
    code = "UNAUTHORIZED"


class NotFoundError(ServiceError):
    status_code = 404
    code = "NOT_FOUND"


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


class InvalidSortError(ServiceError):
    status_code = 400
    code = "INVALID_SORT"


class B2BUnavailableError(ServiceError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"


class B2BRequestError(ServiceError):
    code = "B2B_ERROR"

    def __init__(self, status_code: int, message: str | None = None, code: str | None = None):
        self.status_code = status_code
        self.code = code or self.code
        super().__init__(message)
