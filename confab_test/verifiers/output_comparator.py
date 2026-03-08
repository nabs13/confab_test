"""
Output Comparator — detects suspiciously similar or identical responses
from prompts that should produce different output each time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class Suspicion:
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ComparisonResult:
    identical: bool
    similarity: float          # 0.0 – 1.0 character-level
    matching_numbers: list[str]
    suspicion: str             # Suspicion constant
    reason: str


_NUMBER_RE = re.compile(r"\b\d{4,}\b")  # numbers >= 4 digits are interesting


def _normalise(text: str) -> str:
    """Strip whitespace and lowercase for comparison."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _char_similarity(a: str, b: str) -> float:
    """Simple character-level Jaccard similarity on bigrams."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    def bigrams(s: str) -> set[str]:
        return {s[i : i + 2] for i in range(len(s) - 1)}

    ba, bb = bigrams(a), bigrams(b)
    if not ba and not bb:
        return 1.0
    intersection = ba & bb
    union = ba | bb
    return len(intersection) / len(union)


class OutputComparator:
    def compare(self, response1: str, response2: str) -> ComparisonResult:
        n1 = _normalise(response1)
        n2 = _normalise(response2)

        identical = n1 == n2
        similarity = _char_similarity(n1, n2)

        # Find long numbers that appear in both responses (suspicious for timestamps etc.)
        nums1 = set(_NUMBER_RE.findall(response1))
        nums2 = set(_NUMBER_RE.findall(response2))
        matching_numbers = sorted(nums1 & nums2)

        if identical:
            suspicion = Suspicion.HIGH
            reason = "Responses are byte-for-byte identical after normalisation."
        elif matching_numbers and similarity > 0.7:
            suspicion = Suspicion.HIGH
            reason = (
                f"Responses share long numbers {matching_numbers} "
                f"and are {similarity:.0%} similar."
            )
        elif matching_numbers:
            suspicion = Suspicion.MEDIUM
            reason = f"Responses share numerical values: {matching_numbers}"
        elif similarity > 0.85:
            suspicion = Suspicion.MEDIUM
            reason = f"Responses are very similar ({similarity:.0%}) without being identical."
        elif similarity > 0.5:
            suspicion = Suspicion.LOW
            reason = f"Responses are moderately similar ({similarity:.0%})."
        else:
            suspicion = Suspicion.NONE
            reason = f"Responses differ sufficiently ({similarity:.0%} similarity)."

        return ComparisonResult(
            identical=identical,
            similarity=similarity,
            matching_numbers=matching_numbers,
            suspicion=suspicion,
            reason=reason,
        )
