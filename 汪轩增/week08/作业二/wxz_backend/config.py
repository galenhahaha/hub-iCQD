# -*- coding: utf-8 -*-
"""集中配置：从项目根目录 .env 读取密钥与运行参数。

所有路径都基于本文件（wxz_backend/config.py）定位，保证无论从哪个工作目录启动
（uvicorn wxz_backend.app:app 或 python -m wxz_backend.xxx）都能正确找到 .env / templates / data。
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# 包目录 wxz_backend/
BASE_DIR = Path(__file__).resolve().parent
# 研究记录落盘目录
DATA_DIR = BASE_DIR / "data" / "research"
# Jinja2 提示词模板目录
TEMPLATE_DIR = BASE_DIR / "templates"

# 加载项目根目录的 .env（密钥不提交源码）
load_dotenv(BASE_DIR.parent / ".env")

# --- LLM（DeepSeek，OpenAI 兼容接口）---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/")
MODEL_NAME = os.environ.get("MODEL_NAME", "deepseek-v4-flash")

# --- Bocha 网页搜索 ---
BOCHA_API_KEY = os.environ.get("BOCHA_API_KEY", "")
BOCHA_SEARCH_COUNT = int(os.environ.get("BOCHA_SEARCH_COUNT", "10"))

# --- 研究循环：检索/判断轮数上限 ---
MAX_ROUNDS = int(os.environ.get("RESEARCH_MAX_ROUNDS", "3"))

# --- LLM 空输出重试次数（DeepSeek 偶发 200 但 content 为空）---
LLM_RETRIES = int(os.environ.get("LLM_RETRIES", "3"))


def ensure_data_dir() -> None:
    """幂等地创建落盘目录。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def today_str() -> str:
    """今天的日期（YYYY-MM-DD），用于提示词里的信息截止时间与来源访问时间。"""
    return date.today().isoformat()


if __name__ == "__main__":
    # 自检 demo：打印生效配置并确认落盘目录就绪（纯本地，无需网络/密钥）
    print("BASE_DIR          =", BASE_DIR)
    print("DATA_DIR          =", DATA_DIR)
    print("TEMPLATE_DIR      =", TEMPLATE_DIR)
    print("MODEL_NAME        =", MODEL_NAME)
    print("OPENAI_BASE_URL   =", OPENAI_BASE_URL)
    print("BOCHA_SEARCH_COUNT=", BOCHA_SEARCH_COUNT)
    print("MAX_ROUNDS        =", MAX_ROUNDS)
    print("LLM_RETRIES       =", LLM_RETRIES)
    ensure_data_dir()
    print("DATA_DIR 已就绪:", DATA_DIR.exists())
    print("配置自检 OK")
