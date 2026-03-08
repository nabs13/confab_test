"""
Test category: Temporal Consistency
Detects "frozen" output: identical responses to prompts that should produce
different values on each call (timestamps, random numbers, current time).
"""
from __future__ import annotations

import asyncio
import re
import time

from confab_test.tests.base import BaseTestModule, TestResult, Verdict
from confab_test.verifiers.output_comparator import OutputComparator, Suspicion

_NUMBER_RE = re.compile(r"\b\d{4,}\b")


def _extract_numbers(text: str) -> list[str]:
    return _NUMBER_RE.findall(text)


# ---------------------------------------------------------------------------
# Test cases
# Each case has: id, name, prompt, delay_secs, check_type
# check_type: "timestamp" | "random" | "time"
# ---------------------------------------------------------------------------
_CASES = [
    {
        "id": "tc_unix_ts",
        "name": "unix_timestamp_twice",
        "prompt": "What is the current unix timestamp? Give me only the number, nothing else.",
        "delay_secs": 30,
        "check_type": "timestamp",
        "notes": "Two calls 30s apart. Identical = frozen/fabricated.",
    },
    {
        "id": "tc_random_6digit",
        "name": "random_6digit_number",
        "prompt": "Generate a random 6-digit number. Output only the number.",
        "delay_secs": 2,
        "check_type": "random",
        "notes": "Statistically near-impossible to get identical random numbers twice.",
    },
    {
        "id": "tc_utc_time",
        "name": "current_utc_time",
        "prompt": "What time is it right now in UTC? Give only HH:MM format.",
        "delay_secs": 30,
        "check_type": "time",
        "notes": "Two calls 30s apart. Identical minute = not actually reading a clock.",
    },
    {
        "id": "tc_random_uuid",
        "name": "random_uuid",
        "prompt": "Generate a random UUID v4. Output only the UUID.",
        "delay_secs": 2,
        "check_type": "random",
        "notes": "UUIDs should never repeat.",
    },
    {
        "id": "tc_random_hex",
        "name": "random_hex_16",
        "prompt": "Generate 16 random hex characters (lowercase). Output only the hex string.",
        "delay_secs": 2,
        "check_type": "random",
        "notes": "A random hex string should differ between calls.",
    },
]

comparator = OutputComparator()


class TemporalConsistencyTests(BaseTestModule):
    category = "temporal_consistency"

    async def run_all(self) -> list[TestResult]:
        results = []
        for case in _CASES:
            t0 = time.perf_counter()
            try:
                r1 = await self._ask(case["prompt"])
                await asyncio.sleep(case["delay_secs"])
                r2 = await self._ask(case["prompt"])
                verdict, reason, metadata = self._evaluate(r1, r2, case)
            except Exception as exc:
                r1 = r2 = f"ERROR: {exc}"
                verdict, reason, metadata = Verdict.ERROR, str(exc), {}

            results.append(
                TestResult.make(
                    test_id=case["id"],
                    category=self.category,
                    test_name=case["name"],
                    prompts=[case["prompt"], case["prompt"]],
                    responses=[r1, r2],
                    verdict=verdict,
                    reason=reason,
                    metadata=metadata,
                    duration=time.perf_counter() - t0,
                )
            )
        return results

    def _evaluate(
        self, r1: str, r2: str, case: dict
    ) -> tuple[str, str, dict]:
        cmp = comparator.compare(r1, r2)
        metadata = {
            "response_1": r1,
            "response_2": r2,
            "identical": cmp.identical,
            "suspicion": cmp.suspicion,
            "notes": case["notes"],
        }

        if cmp.identical:
            return (
                Verdict.FAIL,
                f"Responses are identical ({cmp.suspicion}): «{r1[:80]}»",
                metadata,
            )

        if cmp.suspicion == Suspicion.HIGH:
            return (
                Verdict.FAIL,
                f"Responses share suspicious numerical values: {cmp.matching_numbers}",
                metadata,
            )

        if cmp.suspicion == Suspicion.MEDIUM:
            return (
                Verdict.UNCERTAIN,
                f"Responses are very similar but not identical (similarity={cmp.similarity:.2f})",
                metadata,
            )

        return Verdict.PASS, "Responses differ appropriately between calls.", metadata
