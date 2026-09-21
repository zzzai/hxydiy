from collections.abc import Callable
from typing import Any

from fastapi import FastAPI


ADMIN_CATALOG_PREFIXES = (
    "/api/v1/admin/v2/projects",
    "/api/v1/admin/v2/products",
)
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def install_admin_catalog_openapi(app: FastAPI) -> None:
    """Describe the existing bearer contract for the typed admin catalog pilot."""
    default_openapi: Callable[[], dict[str, Any]] = app.openapi

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema

        schema = default_openapi()
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {})["StaffBearer"] = {
            "type": "http",
            "scheme": "bearer",
        }

        for path, path_item in schema.get("paths", {}).items():
            if not path.startswith(ADMIN_CATALOG_PREFIXES):
                continue
            for method, operation in path_item.items():
                if method not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                operation["security"] = [{"StaffBearer": []}]
                operation["parameters"] = [
                    parameter
                    for parameter in operation.get("parameters", [])
                    if not (
                        parameter.get("in") == "header"
                        and parameter.get("name", "").lower() == "authorization"
                    )
                ]

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
