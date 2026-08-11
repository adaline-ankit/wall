from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class Topic(BaseModel):
    name: str
    weight: float = Field(default=1.0, ge=0, le=5)
    keywords: list[str] = Field(default_factory=list)


class SourceSpec(BaseModel):
    type: str = "rss"
    url: HttpUrl
    name: str | None = None
    tags: list[str] = Field(default_factory=list)


class RankingSpec(BaseModel):
    minimum_score: float = Field(default=0.2, ge=0, le=1)
    max_items: int = Field(default=15, ge=1, le=100)
    recency_half_life_hours: int = Field(default=72, ge=1)
    novelty_weight: float = Field(default=0.25, ge=0, le=1)
    source_weights: dict[str, float] = Field(default_factory=dict)


class LearningSpec(BaseModel):
    depth: str = "practitioner"
    assumed_knowledge: list[str] = Field(default_factory=list)
    explain_terms: bool = True

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, value: str) -> str:
        allowed = {"headline", "practitioner", "deep-dive"}
        if value not in allowed:
            raise ValueError(f"depth must be one of: {', '.join(sorted(allowed))}")
        return value


class DeliveryTarget(BaseModel):
    type: str
    url: HttpUrl | None = None
    to: str | None = None
    from_address: str | None = None
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    starttls: bool = True
    username_env: str | None = None
    password_env: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> DeliveryTarget:
        if self.type == "webhook" and self.url is None:
            raise ValueError("webhook delivery requires url")
        if self.type == "email" and not all((self.to, self.from_address, self.smtp_host)):
            raise ValueError("email delivery requires to, from_address, and smtp_host")
        if self.type not in {"webhook", "email"}:
            raise ValueError("delivery target type must be webhook or email")
        return self


class DeliverySpec(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["markdown", "html"])
    output_dir: str = ".wall/output"
    schedule: str | None = None
    targets: list[DeliveryTarget] = Field(default_factory=list)

    @field_validator("formats")
    @classmethod
    def validate_formats(cls, values: list[str]) -> list[str]:
        allowed = {"markdown", "html", "json"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported formats: {', '.join(sorted(unknown))}")
        return values


class LLMConfig(BaseModel):
    provider: str = "none"
    model: str | None = None
    base_url: str | None = None


class WallSpec(BaseModel):
    version: int = 1
    name: str
    goal: str
    topics: list[Topic]
    exclude: list[str] = Field(default_factory=list)
    sources: list[SourceSpec]
    ranking: RankingSpec = Field(default_factory=RankingSpec)
    learning: LearningSpec = Field(default_factory=LearningSpec)
    delivery: DeliverySpec = Field(default_factory=DeliverySpec)
    llm: LLMConfig = Field(default_factory=LLMConfig)


class Item(BaseModel):
    id: str
    title: str
    url: str
    summary: str = ""
    source: str
    published_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tags: list[str] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        HttpUrl(value)
        return value

    @classmethod
    def create(
        cls,
        *,
        title: str,
        url: str,
        summary: str,
        source: str,
        published_at: datetime | None = None,
        tags: list[str] | None = None,
    ) -> Item:
        normalized = url.rstrip("/").lower()
        return cls(
            id=sha256(normalized.encode()).hexdigest()[:16],
            title=title.strip(),
            url=url,
            summary=summary.strip(),
            source=source,
            published_at=published_at or datetime.now(UTC),
            tags=tags or [],
        )


class RankedItem(BaseModel):
    item: Item
    score: float
    reasons: list[str]
    novelty: float
    analysis: str | None = None


class DeliveryReceipt(BaseModel):
    target: str
    status: str
    detail: str | None = None


class WallEdition(BaseModel):
    wall_name: str
    goal: str
    generated_at: datetime
    items: list[RankedItem]
    discovered_count: int
    clustered_count: int
    source_failures: list[str] = Field(default_factory=list)
    delivery_receipts: list[DeliveryReceipt] = Field(default_factory=list)
