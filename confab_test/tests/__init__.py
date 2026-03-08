"""Test modules for confab_test."""
from confab_test.tests.base import TestResult, Verdict

CATEGORY_MAP = {
    "tool_fabrication": "confab_test.tests.test_tool_fabrication",
    "link_verification": "confab_test.tests.test_link_verification",
    "temporal_consistency": "confab_test.tests.test_temporal_consistency",
    "citation_fabrication": "confab_test.tests.test_citation_fabrication",
    "self_knowledge": "confab_test.tests.test_self_knowledge",
    "correction_persistence": "confab_test.tests.test_correction_persistence",
    "number_fabrication": "confab_test.tests.test_number_fabrication",
}

__all__ = ["TestResult", "Verdict", "CATEGORY_MAP"]
