from typing import Generic, List, TypeVar
from pydantic import BaseModel, Field
from app.utils.response import ResponseMeta

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number, 1-indexed")
    page_size: int = Field(default=50, ge=1, le=100, description="Items per page (max 100)")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginatedResult(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 1
        return (self.total + self.page_size - 1) // self.page_size

    def to_meta(self) -> ResponseMeta:
        return ResponseMeta(
            page=self.page,
            page_size=self.page_size,
            total=self.total,
            total_pages=self.total_pages,
        )
