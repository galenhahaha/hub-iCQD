"""Offline parsing and prompt checks: python -m backend.agent."""

import unittest
from unittest.mock import patch

from jinja2 import UndefinedError

from ..models import JudgeDecision, KeywordOutput, ReportOutline
from . import JudgeAgent, KeywordAgent, ReportAgent, SummaryAgent, parse_json


class ParsingTests(unittest.TestCase):
    def test_raw_json(self) -> None:
        output = parse_json('{"keywords": ["检索增强生成", "评测指标"]}', KeywordOutput)
        self.assertEqual(output.keywords, ["检索增强生成", "评测指标"])

    def test_fenced_json(self) -> None:
        payload = '{"sufficient": false, "reason": "缺少证据", "new_keywords": ["性能评测"]}'
        for wrapper in (
            "说明：\n```json\n%s\n```\n结束",
            "```\n%s\n```",
            "```JSON\r\n%s\r\n```",
            "```json %s```",
        ):
            with self.subTest(wrapper=wrapper):
                output = parse_json(wrapper % payload, JudgeDecision)
                self.assertFalse(output.sufficient)
                self.assertEqual(output.new_keywords, ["性能评测"])

    def test_raw_json_containing_backticks(self) -> None:
        output = parse_json('{"keywords": ["```json", "转义字符\\n示例"]}', KeywordOutput)
        self.assertEqual(output.keywords, ["```json", "转义字符\n示例"])

    def test_multiple_fences(self) -> None:
        output = parse_json(
            '```json\n{"wrong": true}\n```\n```json\n{"keywords": ["有效"]}\n```',
            KeywordOutput,
        )
        self.assertEqual(output.keywords, ["有效"])

    def test_invalid_output_is_rejected(self) -> None:
        for payload in (
            "",
            "普通文本而非 JSON",
            '{"keywords": [}',
            '{"wrong": []}',
            '{"keywords": "应当是列表"}',
            '```json\n{"keywords": [1]}\n```',
            '```python\n{"keywords": ["错误围栏类型"]}\n```',
            '```json\n{"keywords": []}',
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "KeywordOutput"):
                    parse_json(payload, KeywordOutput)

    def test_report_outline_nested_references_and_defaults(self) -> None:
        output = parse_json(
            '{"title": "报告", "summary": "摘要", "key_conclusions": ['
            '{"text": "结论", "sources": [{"url": "https://example.com", "title": "来源"}]}]}',
            ReportOutline,
        )
        self.assertEqual(output.key_conclusions[0].sources[0].title, "来源")
        self.assertEqual(output.open_questions, [])
        self.assertNotIn("sections", output.model_dump())


class TemplateTests(unittest.TestCase):
    def test_roles_can_be_constructed_without_credentials(self) -> None:
        for role in (KeywordAgent, SummaryAgent, JudgeAgent, ReportAgent):
            with self.subTest(role=role.__name__):
                self.assertEqual(role(model="offline-model").model, "offline-model")
                self.assertTrue(role().template_name.endswith(".jinja2"))

    def test_all_five_templates_render(self) -> None:
        variables = {"topic": "检索增强生成 & <评测>", "today": "2026-09-08"}
        cases = (
            (KeywordAgent(), None, {}, ("3–5", "keywords")),
            (SummaryAgent(), None, {"keyword": "延迟与召回率"}, ("500–900", "纯文本", "延迟与召回率")),
            (JudgeAgent(), None, {}, ("sufficient", "new_keywords", "searched_keywords")),
            (ReportAgent(), None, {}, ("key_conclusions", "open_questions", "模型推断")),
            (ReportAgent(), "report_html_agent.jinja2", {}, ("<!DOCTYPE html>", "info_cutoff", "HTML 原文")),
        )
        for role, template, extra, markers in cases:
            with self.subTest(template=template or role.template_name):
                prompt = role._render(template, **variables, **extra)
                for expected in (*variables.values(), *markers):
                    self.assertIn(expected, prompt)
                self.assertNotIn("{{", prompt)
                self.assertNotIn("{%", prompt)

    def test_missing_template_variable_fails(self) -> None:
        with self.assertRaises(UndefinedError):
            SummaryAgent()._render(topic="主题", today="2026-09-08")

    def test_topic_is_not_evaluated_as_template_code(self) -> None:
        topic = "研究 {{ 7 * 7 }} 与 {% invalid %}"
        prompt = KeywordAgent()._render(topic=topic, today="2026-09-08")
        self.assertIn(topic, prompt)


if __name__ == "__main__":
    # Fail immediately if a future self-test accidentally tries model or network I/O.
    with (
        patch("backend.agent.base.config.OPENAI_API_KEY", ""),
        patch("backend.agent.base.AsyncOpenAI", side_effect=AssertionError("Offline self-test created an API client")),
        patch("backend.agent.base.Runner.run", side_effect=AssertionError("Offline self-test called the LLM")),
        patch("socket.create_connection", side_effect=AssertionError("Offline self-test attempted network I/O")),
        patch("socket.socket.connect", side_effect=AssertionError("Offline self-test attempted network I/O")),
    ):
        unittest.main(verbosity=2)
