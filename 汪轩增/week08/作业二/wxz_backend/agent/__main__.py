# -*- coding: utf-8 -*-
"""agent 包级自检 demo：python -m wxz_backend.agent（纯本地，不联网）。"""
from .judge import JudgeAgent
from .keyword import KeywordAgent
from .report import ReportAgent
from .summary import SummaryAgent

if __name__ == "__main__":
    print("agent 包导出自检：")
    print("- KeywordAgent:", KeywordAgent().name)
    print("- SummaryAgent:", SummaryAgent().name)
    print("- JudgeAgent:", JudgeAgent().name)
    r = ReportAgent()
    print("- ReportAgent: 内部含", r._outline_agent.name, "+", r._html_agent.name)
    print("agent 包自检 OK")
