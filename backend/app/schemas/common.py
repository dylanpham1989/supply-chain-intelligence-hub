from math import ceil
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field, computed_field


class PaginationParams(BaseModel):
    """Inherited by every filter model.

    FastAPI flattens one pydantic query model per endpoint. A second one is not
    an error: both silently turn into query parameters named after the argument.
    So paging travels with the filters rather than beside them.
    """

    page: int = Field(1, ge=1)
    # Capped so a single request cannot ask for the whole table.
    size: int = Field(50, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


PaginationQuery = Annotated[PaginationParams, Query()]


class Page[ItemT](BaseModel):
    items: list[ItemT]
    total: int
    page: int
    size: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pages(self) -> int:
        return ceil(self.total / self.size) if self.size else 0
