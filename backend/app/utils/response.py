from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseMeta(BaseModel):
    page: Optional[int] = None
    page_size: Optional[int] = None
    total: Optional[int] = None
    total_pages: Optional[int] = None


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error explanation")
    details: Optional[Any] = None


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    meta: Optional[ResponseMeta] = None
    error: Optional[ErrorDetail] = None


def success_response(
    data: Any = None,
    meta: Optional[ResponseMeta] = None,
) -> dict:
    return {
        "success": True,
        "data": data,
        "meta": meta.model_dump() if meta else None,
        "error": None,
    }


def error_response(
    code: str,
    message: str,
    details: Optional[Any] = None,
) -> dict:
    return {
        "success": False,
        "data": None,
        "meta": None,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }
