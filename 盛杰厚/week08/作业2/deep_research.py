"""深度研究助手主入口。

流程（langgraph 状态图）：

    plan ──► search ──► extract ──► judge ──┬─(need_more & 未达上限)─► search
                                            └─(否则)─────────────► write ─► END

用法：
    python deep_research.py --topic "2025-2026 生成式 AI 市场规模与竞争格局"
"""
from __future__ import annotations

import argparse
import os

from langgraph.graph import END, START, StateGraph

from agents.extractor import extractor_node
from agents.judge import judge_node
from agents.planner import planner_node
from agents.searcher import searcher_node
from agents.writer import writer_node
from config import (
    ANTHROPIC_MODEL,
    DEFAULT_MAX_ITERATIONS,
    OPENAI_MODEL,
)
from state import ResearchState
from writers import render_process, render_report, render_sources


# ---------- 路由 ----------

def route_after_judge(state: ResearchState) -> str:
    """Judge 之后：还需补检且未达上限 -> 继续检索；否则 -> 综合成稿。"""
    iteration = int(state.get("iteration", 0))
    max_iterations = int(state.get("max_iterations", DEFAULT_MAX_ITERATIONS))
    if state.get("need_more") and iteration < max_iterations:
        return "search"
    return "write"


# ---------- 图构建 ----------

def build_graph():
    g = StateGraph(ResearchState)
    g.add_node("plan", planner_node)
    g.add_node("search", searcher_node)
    g.add_node("extract", extractor_node)
    g.add_node("judge", judge_node)
    g.add_node("write", writer_node)

    g.add_edge(START, "plan")
    g.add_edge("plan", "search")
    g.add_edge("search", "extract")
    g.add_edge("extract", "judge")
    g.add_conditional_edges("judge", route_after_judge, {"search": "search", "write": "write"})
    g.add_edge("write", END)

    return g.compile()


# ---------- 报告文件渲染 ----------

def _render_outputs(state: ResearchState, out_dir: str) -> dict[str, str]:
    """渲染 report / sources / process 三个 markdown 并写入磁盘。"""
    os.makedirs(out_dir, exist_ok=True)
    files = {
        "report": os.path.join(out_dir, "report.md"),
        "sources": os.path.join(out_dir, "sources.md"),
        "process": os.path.join(out_dir, "process.md"),
    }
    with open(files["report"], "w", encoding="utf-8") as f:
        f.write(render_report(state))
    with open(files["sources"], "w", encoding="utf-8") as f:
        f.write(render_sources(state))
    with open(files["process"], "w", encoding="utf-8") as f:
        f.write(render_process(state))
    return files


# ---------- CLI ----------

def main() -> None:
    ap = argparse.ArgumentParser(description="深度研究助手")
    ap.add_argument("--topic", required=True, help="研究主题")
    ap.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS,
                    help="最大检索轮数（默认 2）")
    ap.add_argument("--out", default="report", help="输出目录")
    ap.add_argument("--provider", choices=["anthropic", "openai"], default=None,
                    help="推理引擎（默认取环境变量 LLM_PROVIDER，缺省 anthropic）")
    ap.add_argument("--model", default=None,
                    help="模型名（覆盖对应 provider 的默认模型）")
    args = ap.parse_args()

    # 通过环境变量把 provider / model 传递给 build_llm（各 Agent 均读取环境变量）
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        if (args.provider or os.environ.get("LLM_PROVIDER", "anthropic")).lower() == "openai":
            os.environ["OPENAI_MODEL"] = args.model
        else:
            os.environ["ANTHROPIC_MODEL"] = args.model

    initial: ResearchState = {
        "topic": args.topic,
        "sub_questions": [],
        "keywords": [],
        "search_history": [],
        "pages_read": [],
        "new_pages": [],
        "rounds": [],
        "evidence": [],
        "iteration": 0,
        "max_iterations": args.max_iterations,
        "need_more": True,
        "sources": [],
        "report": "",
    }

    provider = (args.provider or os.environ.get("LLM_PROVIDER", "anthropic")).lower()
    if args.model:
        model = args.model
    elif provider == "openai":
        model = os.environ.get("OPENAI_MODEL", OPENAI_MODEL)
    else:
        model = os.environ.get("ANTHROPIC_MODEL", ANTHROPIC_MODEL)
    print(f"=== 深度研究助手 ===\n主题：{args.topic}\n推理引擎：{provider} ({model})\n"
          f"最大检索轮数：{args.max_iterations}\n")
    graph = build_graph()
    final = graph.invoke(initial)

    files = _render_outputs(final, args.out)

    n_evidence = len(final.get("evidence", []))
    n_sources = len(final.get("sources", []))
    n_rounds = len(final.get("rounds", []))
    print(f"\n=== 完成 ===")
    print(f"  检索轮数：{n_rounds}  已读页面：{len(final.get('pages_read', []))}  "
          f"证据：{n_evidence}  来源：{n_sources}")
    print(f"  输出目录：{os.path.abspath(args.out)}")
    for k, path in files.items():
        print(f"    - {k}: {path}")


if __name__ == "__main__":
    main()
