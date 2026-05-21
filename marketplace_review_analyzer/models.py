from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, ConfigDict

Marketplace = Literal["WB", "Ozon"]


class Product(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    category: str | None = None
    variant: str | None = None
    wb_url: str | None = None
    wb_article: str | None = None
    ozon_url: str | None = None
    ozon_article: str | None = None

    @property
    def key(self) -> str:
        return "|".join([
            self.name.strip().lower(),
            (self.variant or "").strip().lower(),
            self.wb_article or "",
            self.ozon_article or "",
        ])


class Review(BaseModel):
    marketplace: Marketplace
    product_name: str
    product_article: str | None = None
    rating: int | float | None = None
    text: str = ""
    date: date


class ProblemGroup(BaseModel):
    problem: str
    count: int = 0
    examples: list[str] = Field(default_factory=list)


class ProductReport(BaseModel):
    product: Product
    wb_rating: float | None = None
    ozon_rating: float | None = None
    negative_reviews: list[Review] = Field(default_factory=list)
    problem_groups: list[ProblemGroup] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ProcessingError(BaseModel):
    product_name: str
    marketplace: str
    error_message: str
