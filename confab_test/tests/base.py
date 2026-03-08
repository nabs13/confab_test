"""Base classes and data types shared by all test modules."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class Verdict:
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"
    ERROR = "ERROR"

    SCORE = {PASS: 1.0, FAIL: 0.0, UNCERTAIN: 0.5, ERROR: 0.0}


@dataclass
class TestResult:
    test_id: str
    category: str
    test_name: str
    prompts: list[str]
    responses: list[str]
    verdict: str
    score: float
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        test_id: str,
        category: str,
        test_name: str,
        prompts: list[str],
        responses: list[str],
        verdict: str,
        reason: str,
        metadata: dict | None = None,
        duration: float = 0.0,
    ) -> "TestResult":
        return cls(
            test_id=test_id,
            category=category,
            test_name=test_name,
            prompts=prompts,
            responses=responses,
            verdict=verdict,
            score=Verdict.SCORE[verdict],
            reason=reason,
            metadata=metadata or {},
            duration=duration,
        )


class BaseTestModule(ABC):
    """All test modules must subclass this."""

    category: str = ""

    def __init__(self, client: Any, config: dict) -> None:
        self.client = client
        self.config = config
        self.delay = config.get("tests", {}).get("delay_between", 5)

    @abstractmethod
    async def run_all(self) -> list[TestResult]:
        """Run every test case defined in this module."""
        ...

    async def _ask(self, prompt: str, system: str | None = None) -> str:
        """Send a single prompt, return response text."""
        return await self.client.single(prompt, system=system)

    async def _chat(self, messages: list[dict]) -> str:
        """Send a multi-turn conversation, return final response."""
        return await self.client.chat(messages)

    def _timed(self, fn):
        """Decorator-style helper — not needed since we use async."""
        ...
