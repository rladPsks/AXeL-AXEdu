import json

import pytest

from backend.queries import complaint_stage


@pytest.mark.parametrize("classification, expected", [
    (None, None),
    ({"is_informational": True, "urgency": "LOW"}, "simple"),
    ({"nature": "COMPLAINT", "stage": 2}, "review"),
    ({"nature": "INFRINGEMENT_REVIEW"}, "together"),
    ({"is_informational": True, "urgency": "HIGH"}, "together"),
    ({"stage": 4}, "together"),
])
def test_support_stage_preserves_unknown_and_prioritizes_support(classification, expected):
    assert complaint_stage(json.dumps(classification) if classification is not None else None) == expected
