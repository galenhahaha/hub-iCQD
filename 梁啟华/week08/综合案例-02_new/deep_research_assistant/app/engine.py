"""
深度研究引擎（核心业务流程）
============================
把需求文档定义的业务闭环落成代码：

    规划（拆子问题）→ 多轮检索 → 阅读抽取 → 判断是否补检 → 综合生成报告

最终输出四类成果：
    1. 结构化研究报告（摘要 / 分节正文 / 关键结论 / 遗留问题）
    2. 来源列表（编号 ↔ URL / 标题，可追溯）
    3. 研究过程记录（检索了哪些关键词、读了哪些页面、迭代了几轮）
    4. 置信度说明（可靠性 / 信息截止时间 / 无来源结论标注为“模型推断”）

运行模式：
    - full（完整模式）：配置了 LLM_API_KEY。规划 / 补检判断 / 综合报告都由大模型完成；
    - offline（离线模式）：未配置 LLM 也能跑通 检索 + 阅读，最终用规则拼装“基础报告”，
      并明确标注低置信度 / 模型推断 —— 方便先联调接口，再补 Key 升级为高质量研究。

整个引擎是 async 协程，运行在后台任务里；通过 report(phase, message) 回调
把实时进展抛给外层（任务管理器），从而实现“轮询看进度”的产品体验。
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import Settings
from .llm import LLMClient
from .reader import fetch_page_text
from .search import SearchError, bocha_search

# 进度回调类型：report(阶段名, 人类可读信息)
ReportCallback = Callable[[str, str], None]


# ===========================================================================
# 提示词模板（集中管理，便于后续调优）
# ===========================================================================
_PLAN_SYSTEM = (
    "你是一名严谨的深度研究规划专家。请把用户给定的研究主题拆解为 3~6 个"
    "互不重叠、彼此独立、可单独检索验证的子问题；并为每个子问题给出 1~3 个"
    "能直接用于搜索引擎的具体关键词（避免“最新”“怎么样”这类空泛词）。\n"
    "只输出一个 JSON 对象：\n"
    '{"sub_questions":[{"question":"子问题", "queries":["关键词1","关键词2"]}]}'
)

_JUDGE_SYSTEM = (
    "你是深度研究过程中的质检员。根据目前已获取的网页材料，判断这些材料能否支撑"
    "回答用户的研究主题及其子问题。只有当确实存在明显信息缺口时才要求补检，"
    "避免无意义的重复检索。\n"
    "只输出一个 JSON 对象：\n"
    '{"sufficient": true, "followup_queries": ["补充关键词"], "reason": "一句话说明判断依据"}'
)

_SYNTHESIS_SYSTEM = (
    "你是一名专业的中文研究分析师。请基于下方【来源材料】（每条带编号）撰写一份"
    "结构化研究报告。\n"
    "硬性要求：\n"
    "1. 一切结论都必须来自材料，不得编造；正文引用来源时使用 [编号] 标注；\n"
    "2. 材料支撑不了的推测不要写进正文；\n"
    "3. 关键结论需给出置信度 high/medium/low，以及支撑它的来源编号列表（无材料支撑的"
    "结论 confidence 必须为 low，并把 source_ids 留空）；\n"
    "4. 只输出一个 JSON 对象：\n"
    '{"title":"报告标题","abstract":"200~300字摘要",'
    '"sections":[{"heading":"小节标题","content":"正文，可引用[编号]"}],'
    '"key_conclusions":[{"conclusion":"结论","confidence":"high|medium|low",'
    '"source_ids":[1,2]}],"open_questions":["仍待研究的问题"],'
    '"confidence_notes":{"overall":"总体可靠性说明","info_cutoff":"信息大致截止到什么时间或 未知"}}\n'
    "报告要分节清晰、条理分明、用中文表达。"
)


# ===========================================================================
# 深度研究引擎
# ===========================================================================
class ResearchEngine:
    """深度研究主控：编排 规划 → 检索 → 阅读 → 补检 → 综合。"""

    def __init__(self, settings: Settings, llm: Optional[LLMClient] = None) -> None:
        self.cfg = settings
        self.llm = llm
        self.full_mode = bool(llm is not None and llm.available)
        # 记录本轮已“真实阅读”过的 URL，避免重复抓取同一页面
        self._read_urls: set = set()

    # ------------------------------------------------------------------
    # 对外统一入口
    # ------------------------------------------------------------------
    async def run(
        self,
        topic: str,
        extra_instructions: str = "",
        options: Optional[Dict[str, Any]] = None,
        report: Optional[ReportCallback] = None,
    ) -> Dict[str, Any]:
        """执行一次完整的深度研究。

        参数:
            topic:              研究主题
            extra_instructions: 用户补充要求
            options:            单次任务参数覆盖（max_rounds / results_per_query）
            report:             进度回调，可空
        返回:
            结构化研究报告 dict（含 markdown 渲染文本）
        """
        options = options or {}
        # 轮数 = 1 轮初始检索 + N 轮智能补检
        max_rounds = options.get("max_rounds")
        if max_rounds is None:
            max_rounds = self.cfg.max_rounds
        total_rounds = 1 + max(0, int(max_rounds))

        per_query = options.get("results_per_query") or self.cfg.results_per_query

        # ---------- 研究过程的文字记录（也会随结果一并交付） ----------
        process: List[Dict[str, Any]] = []
        now = lambda: datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

        def say(phase: str, message: str, rnd: Optional[int] = None) -> None:
            """写一条过程日志，并向上回调实时进度。"""
            process.append({"phase": phase, "message": message, "timestamp": now(), "round": rnd})
            if report:
                report(phase, message)

        # 证据池：收集到的所有“候选来源”，后续统一去重、编号、入库
        evidence: List[Dict[str, Any]] = []
        stats = {"rounds_used": 0, "queries_run": 0, "pages_read": 0, "llm_calls": 0}

        # =================================================================
        # 第一步：规划 —— 拆解子问题
        # =================================================================
        say("规划", f"开始拆解研究主题：{topic}")
        sub_questions = await self._plan(topic, extra_instructions, stats)
        say("规划", f"拆解出 {len(sub_questions)} 个子问题（研究模式：{self.cfg.research_mode}）")
        process.append({"stage": "规划", "detail": "子问题列表", "sub_questions": sub_questions})

        # 关键词 → 子问题的反查表，用于把检索来源归类到子问题下
        query_to_question: Dict[str, str] = {}
        for sq in sub_questions:
            for q in sq.get("queries", []):
                query_to_question[q] = sq.get("question", topic)

        # =================================================================
        # 第二步 ~ 第四步：多轮 检索 + 阅读 + 判断补检
        # =================================================================
        followup_queries: List[str] = []
        rounds_done = 0
        for rnd in range(1, total_rounds + 1):
            rounds_done = rnd
            stats["rounds_used"] = rnd

            # 第 1 轮用规划出的关键词；后续轮用“补检”关键词
            if rnd == 1:
                queries: List[str] = self._collect_initial_queries(sub_questions)
            else:
                queries = list(followup_queries)

            if not queries:
                say("检索", "本轮没有可用关键词，结束检索")
                break

            say("检索", f"第 {rnd}/{total_rounds} 轮检索开始，共 {len(queries)} 个关键词", rnd)
            for q in queries:
                stats["queries_run"] += 1
                try:
                    results = await bocha_search(q, per_query, self.cfg)
                except SearchError as exc:
                    say("检索", f"关键词「{q}」检索失败：{exc}")
                    continue
                say("检索", f"关键词「{q}」命中 {len(results)} 条结果", rnd)
                for it in results:
                    it["query"] = q
                    it["question"] = query_to_question.get(q, "")
                    it["round"] = rnd
                    it["page_excerpt"] = ""  # 阅读环节回填
                    evidence.append(it)

            # 阅读抽取：真实抓取部分网页正文（带并发限制），失败则用摘要降级
            stats["pages_read"] = await self._read_pages(evidence, say, stats["pages_read"])

            # 判断是否需要补检（最后一轮无需判断）
            if rnd < total_rounds:
                followup_queries, sufficient, reason = await self._judge(
                    topic, sub_questions, evidence, extra_instructions, stats
                )
                if sufficient or not followup_queries:
                    say("补检", "智能判断：现有材料已足够支撑研究，提前结束检索", rnd)
                    break
                say("补检", f"智能判断仍需补充检索，原因：{reason}", rnd)
            else:
                say("补检", "已达到最大检索轮数，结束检索", rnd)

        # =================================================================
        # 第五步：综合 —— 生成结构化研究报告
        # =================================================================
        say("综合", "检索完成，开始综合生成报告（含来源引用与置信度说明）")

        sources = self._build_sources(evidence)  # 去重 + 编号
        if self.full_mode:
            result = await self._synthesize_with_llm(
                topic, extra_instructions, sub_questions, sources, stats
            )
        else:
            result = self._synthesize_offline(topic, sub_questions, sources)

        # 给“关键结论”补上可追溯的来源 URL（把内部编号解析回真实链接）
        url_by_id = {s["id"]: s["url"] for s in sources}
        for conclusion in result.get("key_conclusions", []):
            ids = [i for i in conclusion.get("source_ids", []) if i in url_by_id]
            conclusion["source_ids"] = ids
            conclusion["source_urls"] = [url_by_id[i] for i in ids]

        # 结果外层打包：四类交付物 + 元信息 + markdown 渲染文本
        result.update(
            {
                "research_mode": self.cfg.research_mode,
                "topic": topic,
                "sources": sources,
                "process_log": process,
                "stats": stats,
                "generated_at": now(),
            }
        )
        result["markdown"] = render_markdown(result)
        say("综合", "研究报告生成完毕")
        return result

    # ------------------------------------------------------------------
    # 规划：拆子问题
    # ------------------------------------------------------------------
    async def _plan(
        self,
        topic: str,
        extra_instructions: str,
        stats: Dict[str, int],
    ) -> List[Dict[str, Any]]:
        """返回 [{"question": "...", "queries": ["..."]}, ...]。"""
        default = [{"question": topic, "queries": [topic]}]

        if not self.full_mode:
            # 离线：没有大模型，就把主题本身作为唯一子问题，保证流程可跑通
            return default

        user = (
            f"研究主题：{topic}\n"
            + (f"补充要求：{extra_instructions}\n" if extra_instructions else "")
            + "请按规则输出子问题与检索关键词。"
        )
        try:
            data = await self.llm.chat_json(_PLAN_SYSTEM, user)
            stats["llm_calls"] += 1
        except Exception:
            # 模型偶发失败时降级，不让整个任务中断
            return default

        items = data.get("sub_questions") or []
        cleaned = []
        for it in items:
            if not isinstance(it, dict):
                continue
            question = str(it.get("question", "")).strip()
            if not question:
                continue
            queries = []
            for q in it.get("queries", []) or []:
                q = str(q).strip()
                if q and q not in queries:
                    queries.append(q)
            if not queries:
                queries = [question]
            cleaned.append({"question": question, "queries": queries[:3]})
        return cleaned[:6] or default

    # ------------------------------------------------------------------
    # 检索关键词收集 / 去重
    # ------------------------------------------------------------------
    @staticmethod
    def _collect_initial_queries(sub_questions: List[Dict[str, Any]]) -> List[str]:
        """汇总所有子问题的检索关键词，去重后返回（控制总量）。"""
        seen: List[str] = []
        for sq in sub_questions:
            for q in sq.get("queries", []):
                if q and q not in seen:
                    seen.append(q)
        return seen[:8]  # 单轮关键词总数上限，防止检索过载

    # ------------------------------------------------------------------
    # 阅读抽取：抓正文
    # ------------------------------------------------------------------
    async def _read_pages(
        self,
        evidence: List[Dict[str, Any]],
        say: ReportCallback,
        already_read: int,
    ) -> int:
        """并发抓取若干来源的网页正文，失败自动跳过（阅读的降级由摘要兜底）。"""
        # 选出尚未读过的候选：优先靠前、信息更全的结果
        candidates = [it for it in evidence if it["url"] and it["url"] not in self._read_urls]
        if not candidates:
            return already_read

        budget = self.cfg.max_pages_to_read - already_read
        targets = candidates[:max(0, budget)]
        if not targets:
            return already_read

        # 限制并发数，避免一瞬间打爆目标站点或自己
        semaphore = asyncio.Semaphore(4)

        async def read_one(item: Dict[str, Any]) -> int:
            """抓取单个页面；成功返回 1，失败返回 0（用于精确统计阅读数）。"""
            async with semaphore:
                text = await fetch_page_text(
                    item["url"],
                    timeout=self.cfg.page_fetch_timeout,
                    max_chars=self.cfg.page_text_max_chars,
                )
                if not text:
                    return 0
                item["page_excerpt"] = text
                say("阅读", f"已阅读正文：{item['name'][:40]}…")
                return 1

        results = await asyncio.gather(*(read_one(it) for it in targets))
        # 记录已“尝试过”的 URL，避免后续重复抓同一页；只累计真正读到的页数
        self._read_urls.update(it["url"] for it in targets)
        return already_read + sum(1 for ok in results if ok)

    # ------------------------------------------------------------------
    # 判断是否需要补检
    # ------------------------------------------------------------------
    async def _judge(
        self,
        topic: str,
        sub_questions: List[Dict[str, Any]],
        evidence: List[Dict[str, Any]],
        extra_instructions: str,
        stats: Dict[str, int],
    ) -> Tuple[List[str], bool, str]:
        """返回 (补检关键词列表, 是否已足够, 原因说明)。"""
        if not self.full_mode or not evidence:
            # 离线模式没有大模型判断，默认视为已足够（可在日志说明）
            return [], True, "离线模式未启用智能补检，本轮材料视为已足够"

        material = self._compact_materials(evidence, limit=10, per_source=180)
        sub_text = "\n".join(f"- {sq['question']}" for sq in sub_questions)
        user = (
            f"研究主题：{topic}\n子问题：\n{sub_text}\n"
            + (f"补充要求：{extra_instructions}\n" if extra_instructions else "")
            + f"【当前已获取的材料】\n{material}\n\n请判断是否需要补检并输出 JSON。"
        )
        try:
            data = await self.llm.chat_json(_JUDGE_SYSTEM, user)
            stats["llm_calls"] += 1
        except Exception:
            return [], True, "补检判断调用失败，按材料已足够处理"

        sufficient = bool(data.get("sufficient", True))
        followups = [str(q).strip() for q in (data.get("followup_queries") or []) if str(q).strip()]
        reason = str(data.get("reason", ""))
        return followups[:3], sufficient, reason

    # ------------------------------------------------------------------
    # 综合（完整模式）：大模型生成结构化报告
    # ------------------------------------------------------------------
    async def _synthesize_with_llm(
        self,
        topic: str,
        extra_instructions: str,
        sub_questions: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        stats: Dict[str, int],
    ) -> Dict[str, Any]:
        material = self._compact_materials(sources, limit=len(sources), per_source=320)
        sub_text = "\n".join(f"- {sq['question']}" for sq in sub_questions)
        user = (
            f"研究主题：{topic}\n预期覆盖的子问题：\n{sub_text}\n"
            + (f"补充要求：{extra_instructions}\n" if extra_instructions else "")
            + f"\n【来源材料】\n{material}\n\n请按规则输出结构化研究报告 JSON。"
        )
        data = await self.llm.chat_json(_SYNTHESIS_SYSTEM, user)
        stats["llm_calls"] += 1

        return self._normalize_report(data, topic)

    # ------------------------------------------------------------------
    # 综合（离线模式）：规则拼装基础报告
    # ------------------------------------------------------------------
    @staticmethod
    def _synthesize_offline(
        topic: str,
        sub_questions: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """无 LLM 时也能产出一份结构完整、来源可追溯的“基础报告”。"""
        # 摘要 = 最相关几条的来源简介拼接
        top_texts = [
            _pick_text(s, 120)
            for s in sources[:4]
            if (s.get("summary") or s.get("snippet"))
        ]
        abstract = "（离线模式）以下为多轮检索得到的公开材料要点汇总：\n" + "\n".join(
            f"- {t}" for t in top_texts
        )

        # 分节：按子问题/检索关键词聚合来源
        sections: List[Dict[str, Any]] = []
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for s in sources:
            key = s.get("question") or f"围绕「{s.get('query')}」的补充材料"
            groups.setdefault(key, []).append(s)
        for heading, items in groups.items():
            lines = []
            for s in items[:6]:
                text = _pick_text(s, 220)
                lines.append(f"- 要点：{text}  （来源 [{s['id']}]）")
            sections.append(
                {"heading": heading, "content": "\n".join(lines), "source_ids": [s["id"] for s in items]}
            )

        return {
            "title": f"{topic} · 深度研究报告（离线版）",
            "abstract": abstract,
            "sections": sections,
            "key_conclusions": [],  # 规则无法产出可靠结论，故留空并在置信度中说明
            "open_questions": [sq["question"] for sq in sub_questions],
            "confidence_notes": {
                "overall": (
                    "离线模式：未接入大模型做语义综合，以下报告仅为检索结果的机械拼接，"
                    "仅用于验证链路与检索覆盖率，不作为结论使用。"
                ),
                "info_cutoff": "以各来源标注时间为准，请查看来源列表",
                "inference_policy": "未配置 LLM，本报告所有观点一律视为“模型推断”，置信度低",
            },
        }

    # ------------------------------------------------------------------
    # 公共小工具
    # ------------------------------------------------------------------
    @staticmethod
    def _compact_materials(
        sources: List[Dict[str, Any]],
        limit: int,
        per_source: int,
    ) -> str:
        """把来源压缩成一段适合塞进提示词的编号材料文本。

        兼容两种输入：
        - 已编号的“最终来源”（含 id 字段，综合环节用）；
        - 未编号的“原始证据”（如补检判断环节用）——此时用枚举序号作编号。
        """
        blocks = []
        for seq, s in enumerate(sources[:limit], start=1):
            sid = s.get("id", seq)          # 有 id 用之，否则用位置序号
            title = s.get("name") or s.get("title") or s.get("url")
            text = _pick_text(s, per_source)
            date = (s.get("date") or "")[:10]
            meta = "，".join(x for x in (date, s.get("site_name")) if x)
            blocks.append(f"[{sid}] 标题：{title}\n    链接：{s.get('url', '')}\n"
                          f"    信息：{meta}\n    内容：{text}")
        return "\n\n".join(blocks)

    @staticmethod
    def _build_sources(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按 URL 去重并编号，截断到报告来源上限。"""
        seen: List[str] = []
        picked: List[Dict[str, Any]] = []
        for it in evidence:
            url = (it.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.append(url)
            picked.append(it)
            if len(picked) >= 25:  # 内建上限，防止报告过长
                break
        # 编号从 1 开始，只保留报告中会展示的字段
        sources = []
        for index, it in enumerate(picked, start=1):
            # snippet：给报告来源列表展示用（来源简介）；
            # text   ：给模型综合用的“阅读材料”（优先真实读到的正文）
            snippet = (it.get("summary") or it.get("snippet") or "")[:300]
            sources.append(
                {
                    "id": index,
                    "title": it.get("name", ""),
                    "url": it.get("url", ""),
                    "site_name": it.get("site_name", ""),
                    "date": it.get("date", ""),
                    "snippet": snippet,
                    "text": _pick_text(it, 800) or snippet,
                    "query": it.get("query", ""),
                    "round": it.get("round", 1),
                    "question": it.get("question", ""),
                }
            )
        return sources

    @staticmethod
    def _normalize_report(data: Dict[str, Any], topic: str) -> Dict[str, Any]:
        """把 LLM 输出规整成统一结构，缺失字段给安全默认值。"""
        sections = []
        for sec in data.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            sections.append(
                {
                    "heading": str(sec.get("heading", "")),
                    "content": str(sec.get("content", "")),
                    "source_ids": _normalize_ids(sec.get("source_ids")),
                }
            )

        conclusions = []
        for c in data.get("key_conclusions") or []:
            if not isinstance(c, dict):
                continue
            conf = str(c.get("confidence", "low")).lower()
            if conf not in ("high", "medium", "low"):
                conf = "low"
            conclusions.append(
                {
                    "conclusion": str(c.get("conclusion", "")),
                    "confidence": conf,
                    "source_ids": _normalize_ids(c.get("source_ids")),
                }
            )

        notes = data.get("confidence_notes") or {}
        if not isinstance(notes, dict):
            notes = {}
        return {
            "title": str(data.get("title") or topic),
            "abstract": str(data.get("abstract", "")),
            "sections": sections,
            "key_conclusions": conclusions,
            "open_questions": [str(x) for x in (data.get("open_questions") or []) if str(x)],
            "confidence_notes": {
                "overall": str(notes.get("overall", "")),
                "info_cutoff": str(notes.get("info_cutoff", "未知")),
                # 统一声明：任何未带来源标注的内容都视为模型推断
                "inference_policy": "正文中未用 [编号] 引用的内容一律视为模型推断",
            },
        }


# ===========================================================================
# 模块级工具函数
# ===========================================================================
def _pick_text(source: Dict[str, Any], length: int) -> str:
    """优先级挑选可读内容：阅读正文 > 智能摘要 > 片段（text 为已整理好的材料字段）。"""
    for key in ("text", "page_excerpt", "summary", "snippet"):
        value = source.get(key) or ""
        if value.strip():
            text = re.sub(r"\s+", " ", value).strip()
            return text[:length]
    return "（无可用正文）"


def _normalize_ids(value: Any) -> List[int]:
    """把模型给的来源编号转成合法的整数列表（兼容字符串 "1,2"、单数字等）。"""
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if isinstance(item, int):
                out.append(item)
            elif isinstance(item, str):
                out.extend(_parse_ids_text(item))
        return list(dict.fromkeys(out))
    if isinstance(value, str):
        return _parse_ids_text(value)
    return []


def _parse_ids_text(text: str) -> List[int]:
    """解析 "1, 3" / "[1,3]" / "1 2" 等字符串形式的编号。"""
    found = re.findall(r"\d+", text)
    return list(dict.fromkeys(int(x) for x in found))


def render_markdown(result: Dict[str, Any]) -> str:
    """把结构化报告渲染成适合阅读/导出的 Markdown 文档。"""
    lines: List[str] = []
    title = result.get("title") or result.get("topic", "")
    lines.append(f"# {title}")
    lines.append("")

    # 元信息
    mode = result.get("research_mode", "")
    generated = result.get("generated_at", "")
    lines.append(f"> 研究主题：{result.get('topic')} ｜ 模式：{mode} ｜ 生成时间：{generated}")
    lines.append("")

    # 摘要
    if result.get("abstract"):
        lines.append("## 摘要")
        lines.append("")
        lines.append(result["abstract"])
        lines.append("")

    # 分节正文
    sections = result.get("sections") or []
    if sections:
        lines.append("## 正文")
        lines.append("")
        for sec in sections:
            heading = sec.get("heading") or "（无标题小节）"
            lines.append(f"### {heading}")
            lines.append("")
            lines.append(sec.get("content", ""))
            ids = sec.get("source_ids") or []
            if ids:
                lines.append("")
                lines.append(f"*本节主要来源：[{'、'.join(f'[{i}]' for i in ids)}]*")
            lines.append("")

    # 关键结论
    conclusions = result.get("key_conclusions") or []
    if conclusions:
        lines.append("## 关键结论")
        lines.append("")
        for c in conclusions:
            conf = c.get("confidence", "low")
            tag = {"high": "🟢 高置信", "medium": "🟡 中置信", "low": "🔴 低置信 / 模型推断"}.get(
                conf, f"置信度 {conf}"
            )
            cites = "".join(f"[{i}]" for i in (c.get("source_ids") or []))
            lines.append(f"- **{c.get('conclusion', '')}**（{tag} {cites}）".rstrip())
        lines.append("")

    # 遗留问题
    open_qs = result.get("open_questions") or []
    if open_qs:
        lines.append("## 遗留问题 / 待进一步研究")
        lines.append("")
        for q in open_qs:
            lines.append(f"- {q}")
        lines.append("")

    # 置信度说明
    notes = result.get("confidence_notes") or {}
    if notes:
        lines.append("## 置信度说明")
        lines.append("")
        lines.append(f"- 总体可靠性：{notes.get('overall') or '未知'}")
        lines.append(f"- 信息截止：{notes.get('info_cutoff') or '未知'}")
        lines.append(f"- 推断政策：{notes.get('inference_policy') or '未标注来源的内容视为模型推断'}")
        lines.append("")

    # 来源列表（可追溯）
    sources = result.get("sources") or []
    if sources:
        lines.append("## 来源列表")
        lines.append("")
        for s in sources:
            title = s.get("title") or s.get("url")
            date = s.get("date", "")[:10]
            site = s.get("site_name", "")
            info = " · ".join(x for x in (site, date) if x)
            lines.append(f"{s['id']}. [{title}]({s.get('url')}){(' — ' + info) if info else ''}")
        lines.append("")

    # 研究过程记录
    process = result.get("process_log") or []
    if process:
        lines.append("## 研究过程记录")
        lines.append("")
        for p in process:
            lines.append(f"- `{p.get('timestamp', '')}` **{p.get('phase')}**：{p.get('message')}")
        lines.append("")

    stats = result.get("stats") or {}
    if stats:
        lines.append("## 过程统计")
        lines.append("")
        lines.append(
            f"- 检索轮次：{stats.get('rounds_used', 0)} ｜ 执行关键词：{stats.get('queries_run', 0)} 个"
            f" ｜ 阅读正文页：{stats.get('pages_read', 0)} ｜ 最终收录来源：{len(sources)} 条"
            f" ｜ LLM 调用：{stats.get('llm_calls', 0)} 次"
        )
        lines.append("")

    return "\n".join(lines)
