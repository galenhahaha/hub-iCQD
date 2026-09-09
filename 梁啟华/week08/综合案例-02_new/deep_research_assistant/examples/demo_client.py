"""
深度研究助手 · 命令行示例客户端
===============================
演示“提交异步任务 → 轮询进度 → 拿到研究报告”的完整调用方式。

用法（先启动服务）：
    python run.py
再开一个终端：
    python examples/demo_client.py --topic "2026年国产大模型市场格局与头部厂商对比"
    python examples/demo_client.py --topic "..." --out report.md
    python examples/demo_client.py --help

原理就是 README 里的两个 HTTP 接口在客户端侧的封装：
    1. POST /api/v1/research          拿到 task_id
    2. GET  /api/v1/research/{id}     循环轮询直到 done/failed
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, Optional

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="深度研究助手示例客户端")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="服务地址，默认 http://127.0.0.1:8000")
    parser.add_argument("--topic", default="2026 年国产大模型市场格局与头部厂商对比",
                        help="研究主题")
    parser.add_argument("--extra", default="", help="补充要求（可选）")
    parser.add_argument("--max-rounds", type=int, default=None,
                        help="覆盖服务端默认的补检轮数（可选）")
    parser.add_argument("--poll-interval", type=float, default=2.0,
                        help="轮询间隔秒数，默认 2 秒")
    parser.add_argument("--timeout", type=float, default=600,
                        help="最大等待秒数，防止无限挂起")
    parser.add_argument("--out", default=None,
                        help="把生成的 Markdown 报告写入该文件（可选）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base = args.base_url.rstrip("/")

    with httpx.Client(timeout=30) as client:
        # ---------- 1) 提交异步任务 ----------
        print(f"▶ 提交研究任务：{args.topic}")
        resp = client.post(
            f"{base}/api/v1/research",
            json={
                "topic": args.topic,
                "extra_instructions": args.extra,
                "max_rounds": args.max_rounds,
            },
        )
        resp.raise_for_status()
        created: Dict[str, Any] = resp.json()
        task_id = created["task_id"]
        print(f"  · task_id = {task_id}  模式 = {created['research_mode']}")
        if created.get("notice"):
            print(f"  · 提示：{created['notice']}")

        # ---------- 2) 轮询进度直到结束 ----------
        print("▶ 轮询中（Ctrl+C 可中断）：")
        seen = 0
        deadline = time.time() + args.timeout
        final: Optional[Dict[str, Any]] = None
        while time.time() < deadline:
            poll = client.get(f"{base}/api/v1/research/{task_id}")
            poll.raise_for_status()
            state: Dict[str, Any] = poll.json()

            # 只打印新出现的阶段消息
            phases = state.get("phases", [])
            for p in phases[seen:]:
                print(f"  [{p.get('timestamp', '')}] {p.get('phase')}: {p.get('message')}")
            seen = len(phases)

            status = state.get("status")
            if status in ("done", "failed"):
                final = state
                break
            time.sleep(args.poll_interval)
        else:
            print(f"✗ 等待超时（{args.timeout}s），任务可能仍在运行")
            return 2

        # ---------- 3) 处理结果 ----------
        if final is None:
            return 2
        if final.get("status") == "failed":
            print(f"✗ 任务失败：{final.get('error')}")
            return 1

        result: Dict[str, Any] = final.get("result") or {}
        markdown = result.get("markdown", "")
        stats = result.get("stats", {})

        print("\n✅ 研究报告生成完毕")
        print(f"   · 标题：{result.get('title')}")
        print(
            f"   · 统计：{stats.get('rounds_used', 0)} 轮 / {stats.get('queries_run', 0)} 个关键词 / "
            f"{stats.get('pages_read', 0)} 页正文 / {len(result.get('sources', []))} 条来源 / "
            f"{stats.get('llm_calls', 0)} 次 LLM 调用"
        )

        # 打印头部一小段预览
        if result.get("abstract"):
            preview = result["abstract"].replace("\n", " ")[:150]
            print(f"\n   摘要预览：{preview}…")

        # 可选：保存完整 Markdown 报告
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(markdown)
            print(f"\n📄 报告已保存：{args.out}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
