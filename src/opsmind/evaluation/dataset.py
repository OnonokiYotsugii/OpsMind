"""Versioned, strict evaluation cases; no executable expressions in datasets."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str | None = None
    arguments: dict = Field(default_factory=dict)
    answer: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def one_action(self):
        if sum(x is not None for x in (self.tool, self.answer, self.error)) != 1:
            raise ValueError("A fixture step has exactly one action.")
        return self


class ToolExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    arguments: dict = Field(default_factory=dict)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    category: Literal[
        "equipment", "classification", "tools", "retrieval", "multistep", "create", "high_risk"
    ]
    kind: Literal["agent", "retrieval"] = "agent"
    prompt: str = Field(min_length=1, max_length=4000)
    expected_status: Literal["completed", "waiting_confirmation", "rejected", "failed"] = (
        "completed"
    )
    expected_error: str | None = None
    scripted_only: bool = False
    expected_label: Literal["electrical", "mechanical", "software", "other"] | None = None
    actor: Literal["EMP-1001", "EMP-1003"] = "EMP-1001"
    required_tools: list[ToolExpectation] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    answer_terms: list[str] = Field(default_factory=list)
    expected_sources: list[str] | None = None
    expected_heading: str | None = None
    require_citation: bool = False
    approval: Literal["none", "approve", "reject"] = "none"
    expected_writes: int = Field(default=0, ge=0, le=1)
    scripted: list[Step] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def coherent(self):
        if self.kind == "retrieval" and self.expected_sources is None:
            raise ValueError("Retrieval cases require relevance labels.")
        if any(e.tool not in self.allowed_tools for e in self.required_tools):
            raise ValueError("Required tools must also be allowed.")
        if self.expected_writes and self.approval != "approve":
            raise ValueError("Expected writes require an explicit test approval.")
        if self.approval != "none" and self.kind != "agent":
            raise ValueError("Only agent cases can approve.")
        return self


def load_cases(path: Path) -> list[Case]:
    cases = [
        Case.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not cases or len(cases) > 100 or len({c.id for c in cases}) != len(cases):
        raise ValueError("Dataset must have 1-100 unique case IDs.")
    return cases
