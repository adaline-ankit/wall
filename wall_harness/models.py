from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class Topic(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    weight: float = Field(default=1.0, ge=0, le=5)
    keywords: list[str] = Field(default_factory=list, max_length=100)


class SourceSpec(BaseModel):
    type: str = "rss"
    url: HttpUrl
    name: str | None = None
    tags: list[str] = Field(default_factory=list)
    cache_ttl_minutes: int = Field(default=30, ge=0, le=1440)


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
    to: str | None = Field(default=None, max_length=320)
    from_address: str | None = Field(default=None, max_length=320)
    smtp_host: str | None = Field(default=None, max_length=253)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    starttls: bool = True
    username_env: str | None = None
    password_env: str | None = None

    @field_validator("to", "from_address")
    @classmethod
    def validate_email_header(cls, value: str | None) -> str | None:
        if value is not None and ("\r" in value or "\n" in value):
            raise ValueError("email addresses cannot contain line breaks")
        return value

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
    provider: Literal["none", "ollama", "openai", "anthropic"] = "none"
    model: str | None = None
    base_url: str | None = None


class EmbeddingConfig(BaseModel):
    provider: Literal["none", "ollama", "openai"] = "none"
    model: str | None = None
    base_url: str | None = None
    similarity_threshold: float = Field(default=0.86, ge=0, le=1)


class WallSpec(BaseModel):
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=5000)
    topics: list[Topic] = Field(min_length=1, max_length=200)
    exclude: list[str] = Field(default_factory=list, max_length=200)
    sources: list[SourceSpec] = Field(min_length=1, max_length=200)
    ranking: RankingSpec = Field(default_factory=RankingSpec)
    learning: LearningSpec = Field(default_factory=LearningSpec)
    delivery: DeliverySpec = Field(default_factory=DeliverySpec)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embeddings: EmbeddingConfig = Field(default_factory=EmbeddingConfig)


class Item(BaseModel):
    id: str = Field(min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$")
    title: str = Field(min_length=1, max_length=2000)
    url: str = Field(max_length=4096)
    summary: str = Field(default="", max_length=100_000)
    source: str = Field(min_length=1, max_length=500)
    published_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tags: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        validated = HttpUrl(value)
        if validated.username or validated.password:
            raise ValueError("item URLs cannot contain credentials")
        return str(validated).rstrip("/")

    @field_validator("published_at")
    @classmethod
    def normalize_published_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_identifier(self) -> Item:
        expected = sha256(self.url.rstrip("/").lower().encode()).hexdigest()[:16]
        if self.id != expected:
            raise ValueError("item id does not match its URL")
        return self

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
        normalized = str(HttpUrl(url)).rstrip("/")
        return cls(
            id=sha256(normalized.lower().encode()).hexdigest()[:16],
            title=title.strip()[:2000],
            url=normalized,
            summary=summary.strip()[:100_000],
            source=source[:500],
            published_at=published_at or datetime.now(UTC),
            tags=(tags or [])[:100],
        )


class RankedItem(BaseModel):
    item: Item
    score: float = Field(ge=0, le=1)
    reasons: list[str]
    novelty: float = Field(ge=0, le=1)
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
    discovered_count: int = Field(ge=0)
    clustered_count: int = Field(ge=0)
    source_failures: list[str] = Field(default_factory=list)
    processing_warnings: list[str] = Field(default_factory=list)
    delivery_receipts: list[DeliveryReceipt] = Field(default_factory=list)
