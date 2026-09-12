"""Safe error responses: never return SQL text, parameters or connection details."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from opsmind.core.errors import BusinessError

logger = logging.getLogger("opsmind.api")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def business_error(_request: Request, exc: BusinessError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request.",
                    "details": details,
                }
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request: Request, _exc: SQLAlchemyError) -> JSONResponse:
        logger.warning("database_integrity_conflict")
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "data_conflict",
                    "message": "Operation conflicts with stored data.",
                }
            },
        )

    @app.exception_handler(OperationalError)
    async def operational_error(request: Request, exc: OperationalError) -> JSONResponse:
        # PyMySQL reports MySQL CHECK violations as OperationalError (3819).
        if exc.orig.args and exc.orig.args[0] == 3819:
            return await integrity_error(request, exc)
        return await database_error(request, exc)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, _exc: SQLAlchemyError) -> JSONResponse:
        logger.error("database_operation_failed")
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": "Database operation unavailable.",
                }
            },
        )
