from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.router import api_router
from src.core.config import settings
from src.services.errors import ServiceError

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="NeoMarket B2C service",
)
app.include_router(api_router)


@app.get("/healthz", tags=["Health"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(ServiceError)
async def service_error_handler(_, exc: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = first_error.get("loc", ())
    field = location[-1] if location else "request"
    message = first_error.get("msg", "Request validation failed")
    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "message": f"{field}: {message}"},
    )

