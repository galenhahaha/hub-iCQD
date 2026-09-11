"""深度研究助手 - 智能版 v2

核心优化：
- LLM 智能生成子问题（无硬编码模板）
- 中文专业报告结构
- 修复轮次统计
- API Key 环境变量配置
"""

# 先加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from datetime import datetime
from typing import List, Dict, Set, Tuple
import json
import os

# ============== 配置校验 ==============
SF_API_KEY = os.getenv("SF_API_KEY")
SF_API_URL = os.getenv("SF_API_URL", "https://api.siliconflow.cn/v1/chat/completions")
SF_MODEL = os.getenv("SF_MODEL", "Pro/MiniMaxAI/MiniMax-M2.5")


def check_api_key() -> bool:
    """检查 API Key 是否配置有效"""
    if not SF_API_KEY:
        st.error("⚠️ 未检测到有效的 SF_API_KEY！请在项目根目录创建 .env 文件并配置密钥后再重新加载页面。")
        st.info("📝 .env 文件格式参考：")
        st.code("""# SiliconFlow API
SF_API_KEY=your_api_key_here
SF_API_URL=https://api.siliconflow.cn/v1/chat/completions
SF_MODEL=Pro/MiniMaxAI/MiniMax-M2.5""")
        st.stop()
        return False
    if SF_API_KEY.startswith("sk-") and len(SF_API_KEY) < 20:
        st.error("⚠️ SF_API_KEY 格式无效，请检查配置。")
        st.stop()
        return False
    return True


# ============== LLM 客户端 ==============
def call_llm(prompt: str, temperature: float = 0.7) -> str:
    """调用 LLM 生成内容

    Args:
        prompt: 提示词
        temperature: 温度参数

    Returns:
        LLM 生成的文本
    """
    import requests

    headers = {
        "Authorization": f"Bearer {SF_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": SF_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 2000
    }

    try:
        response = requests.post(SF_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        st.error(f"LLM 调用失败: {e}")
        return ""


def plan_subqueries_with_llm(topic: str, max_rounds: int) -> List[Dict]:
    """使用 LLM 智能生成子问题（中英双语）

    Args:
        topic: 研究主题
        max_rounds: 最大轮次

    Returns:
        子问题列表，每个包含 {search_query, angle, english_query}
    """
    prompt = f"""你是一个专业的研究助手。请为以下研究主题生成 {max_rounds} 个精准、有针对性的搜索关键词。

要求：
1. 每个搜索词必须自然、简洁，不超过 20 字
2. 必须与主题直接相关，能搜到真实有效的内容
3. 不要使用"定义"、"概念"、"历史"等空洞后缀
4. 【关键】必须同时生成中文关键词和对应的英文学术术语
5. 每个查询包含：1个中文硬核关键词 + 1个对应的英文学术专有名词

研究主题：{topic}

请直接输出 JSON 数组格式，每项包含：
- "query": 中文搜索关键词
- "english_query": 对应的英文学术术语（如 "Neuro-symbolic RAG"、"Multi-hop reasoning"）
- "angle": 研究角度（2-4字）

示例输出（主题：RAG大模型幻觉问题）：
[
  {{"query": "RAG 检索增强 事实性幻觉", "english_query": "retrieval-augmented generation hallucination", "angle": "问题定义"}},
  {{"query": "Multi-hop reasoning 知识追踪", "english_query": "multi-hop reasoning knowledge tracing", "angle": "技术原理"}},
  {{"query": "Neuro-symbolic RAG 语义对齐", "english_query": "neuro-symbolic RAG semantic alignment", "angle": "解决方案"}}
]

请直接输出 JSON，不要其他解释："""

    result = call_llm(prompt)

    try:
        # 尝试解析 JSON
        # 去掉可能的 markdown 代码块标记
        result = result.strip()
        if result.startswith("```"):
            result = result.split("```")[1]
            if result.startswith("json"):
                result = result[4:]
        if result.startswith("```"):
            result = result[3:]
        result = result.strip().rstrip("```")

        subqueries = json.loads(result)

        # 验证格式
        valid_subqueries = []
        for sq in subqueries:
            if isinstance(sq, dict) and "query" in sq:
                valid_subqueries.append({
                    "search_query": sq["query"],
                    "english_query": sq.get("english_query", sq["query"]),
                    "angle": sq.get("angle", "研究"),
                    "chinese": sq["query"]
                })

        return valid_subqueries[:max_rounds]

    except json.JSONDecodeError:
        st.warning("LLM 返回格式错误，使用备选方案")
        return fallback_plan_subqueries(topic, max_rounds)


def fallback_plan_subqueries(topic: str, max_rounds: int) -> List[Dict]:
    """备选方案：当 LLM 调用失败时的子问题生成"""
    # 简单按关键词切分
    words = topic.replace("的", " ").replace("在", " ").replace("与", " ").split()
    keywords = [w for w in words if len(w) >= 2][:5]

    if len(keywords) >= 2:
        queries = []
        for i in range(min(max_rounds, len(keywords))):
            if i + 1 < len(keywords):
                queries.append({
                    "search_query": f"{keywords[i]} {keywords[i+1]}",
                    "english_query": f"{keywords[i]} {keywords[i+1]}",
                    "angle": "研究",
                    "chinese": f"{keywords[i]} {keywords[i+1]}"
                })
            else:
                queries.append({
                    "search_query": keywords[i],
                    "english_query": keywords[i],
                    "angle": "研究",
                    "chinese": keywords[i]
                })
        return queries[:max_rounds]
    else:
        return [{"search_query": topic, "english_query": topic, "angle": "研究", "chinese": topic}]


# ============== 搜索工具 ==============
from tools import web_search, extract_key_entities, is_english_query


def init_session_state():
    """初始化会话状态"""
    if "research_log" not in st.session_state:
        st.session_state.research_log = []
    if "sources" not in st.session_state:
        st.session_state.sources = []
    if "findings" not in st.session_state:
        st.session_state.findings = []
    if "report" not in st.session_state:
        st.session_state.report = None
    if "search_failed" not in st.session_state:
        st.session_state.search_failed = []


def log(message: str):
    """记录研究日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.research_log.append({"time": timestamp, "message": message})


def run_research_round(topic: str, sub_query: Dict, round_num: int) -> Dict:
    """执行单轮研究"""
    search_query = sub_query["search_query"]
    angle = sub_query.get("angle", "研究")

    log(f"轮次 {round_num}: 搜索「{search_query}」(角度: {angle})")

    results = web_search(search_query, count=5)

    if not results:
        log(f"⚠️ 未找到「{search_query}」的真实结果")
        st.session_state.search_failed.append(search_query)
        return {
            "round": round_num,
            "query": search_query,
            "angle": angle,
            "results_count": 0,
            "findings": []
        }

    log(f"   ✓ 获取到 {len(results)} 条真实结果")

    findings = []
    for r in results:
        findings.append({
            "title": r["title"],
            "url": r["url"],
            "snippet": r["snippet"],
            "angle": angle
        })
        st.session_state.sources.append((r["title"], r["url"]))

    return {
        "round": round_num,
        "query": search_query,
        "angle": angle,
        "results_count": len(results),
        "findings": findings
    }


def synthesize_findings(findings: List[Dict], failed_keywords: List[str]) -> Dict:
    """综合研究发现"""
    if not findings:
        return {"summary": "未获取到有效研究数据", "key_facts": [], "by_angle": {}}

    # 按角度分组
    by_angle = {}
    for f in findings:
        angle = f.get("angle", "研究")
        if angle not in by_angle:
            by_angle[angle] = []
        by_angle[angle].append(f)

    # 提取关键信息
    key_facts = []
    for f in findings:
        snippet = f["snippet"].replace("\n", " ").strip()
        if len(snippet) > 30:
            key_facts.append({
                "title": f["title"],
                "url": f["url"],
                "snippet": snippet[:250] + "..." if len(snippet) > 250 else snippet,
                "angle": f.get("angle", "研究")
            })

    summary = f"本研究收集了 {len(findings)} 条信息，涵盖 {len(by_angle)} 个研究角度。"
    if failed_keywords:
        summary += f" 有 {len(failed_keywords)} 个查询未获结果。"

    return {
        "summary": summary,
        "key_facts": key_facts,
        "by_angle": by_angle,
        "failed_keywords": failed_keywords
    }


def generate_report(topic: str, synthesized: Dict, unique_sources: List[Tuple], round_count: int) -> str:
    """生成专业中文章节结构报告"""
    log("生成结构化报告...")

    report = f"""# {topic}

## 摘要

{synthesized['summary']}

本报告基于真实网络检索，所有内容可追溯验证。

---

"""

    # 按角度分组生成章节
    by_angle = synthesized.get("by_angle", {})
    if by_angle:
        report += "## 研究发现\n\n"

        angle_order = list(by_angle.keys())
        for i, angle in enumerate(angle_order, 1):
            facts = by_angle[angle]
            report += f"### {i}. {angle}\n\n"

            for fact in facts[:4]:  # 每角度最多4条
                report += f"**{fact['title']}**\n\n"
                report += f"{fact['snippet']}\n\n"
                report += f"[查看原文]({fact['url']})\n\n"

            report += "---\n\n"

    # 未决问题
    report += "## 待深入研究的问题\n\n"

    failed = synthesized.get("failed_keywords", [])
    if failed:
        for kw in failed:
            report += f"- 关于「{kw}」的更多信息（本次未获取到有效结果）\n"
    else:
        report += "- 本研究已覆盖主要方面，建议根据实际需求进一步聚焦\n"

    # 参考文献
    report += "\n## 参考文献\n\n"
    for title, url in unique_sources:
        report += f"- [{title}]({url})\n"

    # 元信息
    report += f"""
---

*报告生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
*实际执行轮次：{round_count} 轮*

## 置信度评估

| 评估维度 | 评级 | 说明 |
|----------|------|------|
| 信息来源 | {"有效" if synthesized['key_facts'] else "无"} | 来自真实网络检索 |
| 覆盖面 | {"中等" if len(by_angle) > 1 else "有限"} | {f"涵盖 {len(by_angle)} 个角度" if by_angle else "数据不足"} |
| 可追溯性 | 高 | 每条信息含原文链接 |

**整体评估**：{len(synthesized['key_facts'])} 条有效信息，{len(unique_sources)} 个来源

---

*本报告内容完全基于公开网络资源生成，无任何虚构内容。*
"""

    return report


def main():
    st.set_page_config(page_title="深度研究助手", page_icon="🔬", layout="wide")

    # 启动时校验 API Key
    check_api_key()

    init_session_state()

    st.title("🔬 深度研究助手")
    st.markdown("基于 LLM 智能规划 + 真实网络检索的研究工具")

    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 研究设置")
        topic = st.text_input("研究主题")
        max_rounds = st.slider("检索轮次", min_value=1, max_value=5, value=3)

        st.caption("🔒 仅使用真实搜索结果，无 Mock 数据")

        if st.button("🚀 开始研究", type="primary", use_container_width=True):
            # 清空状态
            st.session_state.research_log = []
            st.session_state.sources = []
            st.session_state.findings = []
            st.session_state.report = None
            st.session_state.search_failed = []

            # 开始研究
            log(f"开始研究: {topic}")

            # 使用 LLM 生成智能子问题
            with st.status("🤔 规划研究方案...", expanded=True) as status:
                st.write("正在使用 AI 生成搜索词...")
                sub_queries = plan_subqueries_with_llm(topic, max_rounds)

                log(f"生成 {len(sub_queries)} 个搜索词")
                for sq in sub_queries:
                    log(f"  - {sq['search_query']} ({sq.get('angle', '研究')})")

                status.update(label="🔬 执行检索中...", state="running")

                # 执行检索
                all_findings = []
                actual_rounds = 0

                for i, sq in enumerate(sub_queries[:max_rounds], 1):
                    actual_rounds = i
                    st.write(f"**轮次 {i}**: {sq['search_query']}")

                    result = run_research_round(topic, sq, i)
                    all_findings.extend(result["findings"])

                    if result["results_count"] > 0:
                        st.write(f"   ✓ {result['results_count']} 条结果")
                    else:
                        st.write("   ⚠️ 无结果")

                # 综合与报告
                synthesized = synthesize_findings(all_findings, st.session_state.search_failed)

                # URL 去重
                seen = set()
                unique = []
                for t, u in st.session_state.sources:
                    if u and u not in seen:
                        seen.add(u)
                        unique.append((t, u))

                # 生成报告（传入实际轮次）
                report = generate_report(topic, synthesized, unique, actual_rounds)
                st.session_state.report = report

                log(f"研究完成！执行了 {actual_rounds} 轮")

                status.update(label="✅ 完成", state="complete")

        if st.button("🗑️ 清空结果", use_container_width=True):
            st.session_state.research_log = []
            st.session_state.sources = []
            st.session_state.findings = []
            st.session_state.report = None
            st.session_state.search_failed = []
            st.rerun()

    # 主界面
    if not topic:
        st.info("👈 请输入研究主题并点击开始研究")
        return

    # 显示结果
    if st.session_state.report or st.session_state.sources:
        tab1, tab2, tab3 = st.tabs(["📄 报告", "📚 来源", "📋 日志"])

        with tab1:
            if st.session_state.report:
                st.markdown(st.session_state.report)
            else:
                st.info("点击「开始研究」生成报告")

        with tab2:
            if st.session_state.sources:
                seen = set()
                for title, url in st.session_state.sources:
                    if url and url not in seen:
                        seen.add(url)
                        st.markdown(f"- [{title}]({url})")
                st.caption(f"共 {len(seen)} 个唯一来源")
            else:
                st.info("无来源")

        with tab3:
            if st.session_state.research_log:
                for e in st.session_state.research_log:
                    st.markdown(f"`{e['time']}` {e['message']}")
            else:
                st.info("暂无日志")


if __name__ == "__main__":
    main()