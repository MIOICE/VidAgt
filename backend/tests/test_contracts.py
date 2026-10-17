import pytest
from pydantic import ValidationError

from app.agents.contracts import AnalysisPlan, VideoReport


def test_plan_rejects_more_than_five_steps() -> None:
    with pytest.raises(ValidationError):
        AnalysisPlan(
            title="too many",
            steps=[
                {"id": f"step_{index}", "objective": "目标", "search_query": "查询"}
                for index in range(6)
            ],
        )


def test_report_requires_confidence_in_range() -> None:
    with pytest.raises(ValidationError):
        VideoReport(
            title="报告",
            executive_summary="摘要",
            chapters=[],
            conclusions=[{"text": "结论", "evidence_ids": [], "confidence": 1.2}],
            action_items=[],
            suggestions=[],
        )

