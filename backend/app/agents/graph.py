from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.contracts import AnalysisPlan, Critique, Finding, VideoReport
from app.agents.retrieval import hybrid_retrieve
from app.core.database import SessionLocal
from app.models.entities import AnalysisRun
from app.services.ai_provider import ai_provider


class AgentState(TypedDict, total=False):
    analysis_id: str
    video_id: str
    goal: str
    language: str
    evidence: list[dict[str, Any]]
    plan: dict[str, Any]
    findings: list[dict[str, Any]]
    critique: dict[str, Any]
    revision_count: int
    report: dict[str, Any]


def _evidence_text(items: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[{item['id']}] {item['start_ms']}~{item['end_ms']}ms {item['source']}: {item['content']}"
        for item in items
    )


async def retrieve_node(state: AgentState) -> dict[str, Any]:
    async with SessionLocal() as db:
        items = await hybrid_retrieve(db, state["video_id"], state["goal"], top_k=8)
    return {"evidence": [item.model_dump() for item in items]}


async def planner_node(state: AgentState) -> dict[str, Any]:
    plan = await ai_provider.json_completion(
        AnalysisPlan,
        "你是视频分析规划器。将目标拆成少量、互不重复且可由视频证据回答的任务。",
        f"分析目标：{state['goal']}\n可用证据：\n{_evidence_text(state['evidence'])[:16000]}",
    )
    async with SessionLocal() as db:
        analysis = await db.get(AnalysisRun, state["analysis_id"])
        if analysis:
            analysis.plan = plan.model_dump()
            analysis.progress = 0.3
            await db.commit()
    return {"plan": plan.model_dump(), "revision_count": 0}


async def executor_node(state: AgentState) -> dict[str, Any]:
    evidence_text = _evidence_text(state["evidence"])
    feedback = state.get("critique", {}).get("feedback", "")
    findings: list[dict[str, Any]] = []
    valid_ids = {item["id"] for item in state["evidence"]}
    for step in state["plan"]["steps"]:
        finding = await ai_provider.json_completion(
            Finding,
            "你是视频证据分析器。只能根据给定证据作答，不得编造。evidence_ids 只能引用输入中的ID。",
            (
                f"任务：{json.dumps(step, ensure_ascii=False)}\n"
                f"上一轮反馈：{feedback or '无'}\n证据：\n{evidence_text[:24000]}"
            ),
        )
        finding.evidence_ids = [item for item in finding.evidence_ids if item in valid_ids]
        findings.append(finding.model_dump())
    return {"findings": findings}


async def critic_node(state: AgentState) -> dict[str, Any]:
    critique = await ai_provider.json_completion(
        Critique,
        "你是严格的分析审查器，检查目标覆盖、证据一致性和结论完整性。",
        (
            f"目标：{state['goal']}\n计划：{json.dumps(state['plan'], ensure_ascii=False)}\n"
            f"分析结果：{json.dumps(state['findings'], ensure_ascii=False)}"
        ),
    )
    return {
        "critique": critique.model_dump(),
        "revision_count": state.get("revision_count", 0) + (0 if critique.approved else 1),
    }


def critic_route(state: AgentState) -> str:
    critique = state["critique"]
    if not critique["approved"] and state.get("revision_count", 0) < 2:
        return "revise"
    return "synthesize"


async def synthesize_node(state: AgentState) -> dict[str, Any]:
    report = await ai_provider.json_completion(
        VideoReport,
        "你是视频报告编辑。输出简洁、有层次、可追溯的最终报告，不得引用不存在的证据。",
        (
            f"目标：{state['goal']}\n语言：{state['language']}\n"
            f"分析：{json.dumps(state['findings'], ensure_ascii=False)}\n"
            f"证据：{_evidence_text(state['evidence'])[:24000]}"
        ),
    )
    valid_ids = {item["id"] for item in state["evidence"]}
    for conclusion in report.conclusions:
        conclusion.evidence_ids = [item for item in conclusion.evidence_ids if item in valid_ids]
    return {"report": report.model_dump()}


def build_analysis_graph():
    builder = StateGraph(AgentState)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("plan", planner_node)
    builder.add_node("execute", executor_node)
    builder.add_node("critic", critic_node)
    builder.add_node("synthesize", synthesize_node)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "plan")
    builder.add_edge("plan", "execute")
    builder.add_edge("execute", "critic")
    builder.add_conditional_edges(
        "critic", critic_route, {"revise": "execute", "synthesize": "synthesize"}
    )
    builder.add_edge("synthesize", END)
    return builder.compile(checkpointer=MemorySaver())


async def invoke_analysis(analysis: AnalysisRun) -> dict[str, Any]:
    graph = build_analysis_graph()
    result = await graph.ainvoke(
        {
            "analysis_id": analysis.id,
            "video_id": analysis.video_id,
            "goal": analysis.goal,
            "language": analysis.language,
        },
        config={"configurable": {"thread_id": analysis.graph_thread_id}},
    )
    return result["report"]

