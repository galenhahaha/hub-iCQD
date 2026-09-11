#!/usr/bin/env python3
"""
Claude Code Hook: 检测用户提示词中是否包含敏感密钥并拦截
事件: user_prompt_submit
"""

import sys
import json
import re

# 常见密钥正则（可根据需要扩展）
SECRET_PATTERNS = [
    # OpenAI / Anthropic / 通用 API Key
    re.compile(r'(sk-[A-Za-z0-9]{20,})'),
    re.compile(r'(sk-proj-[A-Za-z0-9\-_]{20,})'),
    # AWS Access Key
    re.compile(r'(AKIA[0-9A-Z]{16})'),
    # Google API Key
    re.compile(r'(AIza[0-9A-Za-z\-_]{35})'),
    # GitHub Personal Access Token
    re.compile(r'(ghp_[A-Za-z0-9]{36})'),
    re.compile(r'(gho_[A-Za-z0-9]{36})'),
    # Generic "Bearer" or "Token" in plain text (可选)
    re.compile(r'(?:Bearer|token)\s*[:=]\s*[\'"]?([A-Za-z0-9\-_.]{20,})', re.IGNORECASE),
    # 通用高熵字符串（长度 > 32 且含大小写字母数字，误报风险较高，谨慎启用）
    # 若需要可取消注释下方行
    # re.compile(r'\b[A-Za-z0-9+/]{40,}\b'),
]


def has_secret(text: str) -> bool:
    """检查文本中是否包含任何匹配的密钥模式"""
    if not text:
        return False
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


def main():
    # 从标准输入读取 JSON（用 buffer 读原始字节，再显式按 UTF-8 解码，
    # 避免 Windows 上 sys.stdin 默认按 GBK/cp936 解码中文导致 UnicodeDecodeError）
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        payload = json.loads(raw)
    except Exception as e:
        # 如果解析失败，允许继续（避免误阻断）
        print(json.dumps({"continue": True}))
        return

    # 提取用户输入的 prompt（UserPromptSubmit 的 JSON 中 prompt 在顶层）
    prompt = payload.get("prompt", "")

    if has_secret(prompt):
        # 拦截并提示
        result = {
            "continue": False,
            "stopReason": "⚠️ 检测到您输入了类似 API Key 的敏感信息，请勿在对话中直接粘贴密钥。"
                          " 您可以将密钥放入环境变量或配置文件中，然后引用变量名。"
        }
    else:
        result = {"continue": True}

    # 输出 JSON 结果
    print(json.dumps(result))


if __name__ == "__main__":
    main()