from pydantic import BaseModel, ConfigDict, Field


class DocumentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    document_type: str = Field(min_length=1, max_length=32, pattern=r"^[a-z_]+$")
    source: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:/-]+$")
    version: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=3, ge=1, le=5, strict=True)
    source: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=32)
