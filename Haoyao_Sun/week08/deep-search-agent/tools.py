"""搜索工具模块 - 支持英文搜索与语义相关性过滤"""

import logging
from typing import List, Dict, Set, Tuple
import re

# 先加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# 尝试导入 ddgs
try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False
        logger.error("ddgs/duckduckgo-search 未安装")


# 排除的通用词
EXCLUDE_WORDS = {
    'the', 'and', 'for', 'with', 'from', 'into', 'about',
    'this', 'that', 'what', 'when', 'where', 'which', 'who',
    'committee', 'organization', 'history', 'about', 'company',
    'corporation', 'association', 'foundation', 'american'
}

# 噪音声称类型（需要过滤的页面类型）
NOISE_PATTERNS = [
    # 词典释义
    (r'^(definition|definition of|词源|词典|词典释义)', 'dictionary'),
    # 不相关的代码库/仓库
    (r'^(github|gitlab|bitbucket|pypi|npm|cargo|crates\.io)', 'code_repo'),
    # 语音模型/音频
    (r'(tts|text-to-speech|语音合成|语音模型|elevenlabs|coqui)', 'tts'),
    # 词典查询结果
    (r'(urban dictionary|merriam-webster|collins|cambridge dictionary)', 'dictionary'),
    # 无关的 FAQ
    (r'(faq|frequently asked questions)$', 'faq'),
    # 招聘/工作
    (r'(jobs|careers|招聘|职位需求)$', 'jobs'),
]


def filter_relevance(result: dict, topic: str, key_entities: Set[str]) -> Tuple[bool, str]:
    """语义相关性过滤 - 噪声剔除机制

    丢弃与主题无关的页面（如词典释义、语音模型、不相干的代码库）。

    Args:
        result: 搜索结果 {title, url, snippet}
        topic: 研究主题
        key_entities: 关键实体集合

    Returns:
        (是否相关, 拒绝原因)
    """
    title = result.get('title', '').lower()
    url = result.get('url', '').lower()
    snippet = result.get('snippet', '').lower()
    text = f"{title} {url} {snippet}"

    # 1. 检查噪声音牌类型
    for pattern, noise_type in NOISE_PATTERNS:
        if re.search(pattern, url) or re.search(pattern, title):
            return False, noise_type

    # 2. 检查 URL 域名是否完全不相关（如纯代码仓库但内容不匹配）
    code_domains = ['github.com', 'pypi.org', 'npmjs.com', 'crates.io']
    for domain in code_domains:
        if domain in url:
            # 需要有内容匹配才保留
            if key_entities:
                matches = sum(1 for e in key_entities if e in text)
                if matches == 0:
                    return False, "unrelated_code"

    # 3. 检查是否是纯粹的词典释义页面
    if len(snippet) < 50 and ('词性' in result.get('snippet', '') or re.match(r'^[A-Z][a-z]+ is (a|an)', result.get('snippet', ''))):
        # 短摘要可能是词典定义的特征
        if not key_entities:
            return False, "dictionary"

    # 4. 如果有关键实体，确保至少匹配一个
    if key_entities:
        matches = sum(1 for e in key_entities if e.lower() in text)
        if matches == 0:
            # 尝试部分匹配
            partial = False
            for e in key_entities:
                words = e.split()
                if len(words) >= 2:
                    matched = sum(1 for w in words if w.lower() in text)
                    if matched >= len(words) - 1:
                        partial = True
                        break
            if not partial:
                return False, "no_entity_match"

    # 5. 检查主题关键词覆盖
    topic_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', topic.lower())) - EXCLUDE_WORDS
    if topic_words:
        matches = sum(1 for w in topic_words if w in text)
        if matches == 0:
            # 尝试中文关键词
            cn_words = re.findall(r'[一-鿿]{2,}', topic)
            if cn_words:
                cn_matches = sum(1 for w in cn_words if w in result.get('snippet', ''))
                if cn_matches == 0:
                    return False, "no_topic_match"

    return True, ""


def extract_key_entities(topic: str) -> Tuple[Set[str], Set[str]]:
    """从研究主题中提取关键实体（分层：完整实体 + 单词）

    Args:
        topic: 研究主题

    Returns:
        (full_entities, key_words) 元组
    """
    full_entities = set()
    key_words = set()

    # 1. 提取连续的英文词组（1-4个单词）
    pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4})\b'
    matches = re.findall(pattern, topic)
    for m in matches:
        if m.lower() not in EXCLUDE_WORDS and len(m) > 2:
            full_entities.add(m)

    # 2. 提取包含组织类型后缀的机构名（优先级最高，放前面）
    org_patterns = [
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Committee|Association|Foundation|Corporation|Organization|Movement|Party|Union))',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:First|Second|Third|Fourth)\s+(?:Committee|Organization|Movement))',
    ]
    for p in org_patterns:
        matches = re.findall(p, topic, re.IGNORECASE)
        for m in matches:
            m = m.strip()
            if m.lower() not in EXCLUDE_WORDS:
                full_entities.add(m)

    # 3. 分词提取关键词（如果没有完整实体）
    if not full_entities:
        words = re.findall(r'\b[a-zA-Z]{4,}\b', topic)
        for w in words:
            if w.lower() not in EXCLUDE_WORDS:
                key_words.add(w.lower())
    else:
        # 从完整实体中提取关键词
        for entity in full_entities:
            parts = entity.split()
            for p in parts:
                if p.lower() not in EXCLUDE_WORDS and len(p) > 2:
                    key_words.add(p.lower())

    return full_entities, key_words


def is_relevant_old(result: dict, full_entities: Set[str], key_words: Set[str], topic: str) -> bool:
    """检查搜索结果是否与研究主题相关

    Args:
        result: 搜索结果 {title, url, snippet}
        full_entities: 完整实体集合
        key_words: 关键词集合
        topic: 原始研究主题

    Returns:
        True 表示相关，False 表示不相关
    """
    title = result.get('title', '').lower()
    snippet = result.get('snippet', '').lower()
    text = f"{title} {snippet}"

    # 1. 优先检查完整实体匹配
    if full_entities:
        for entity in full_entities:
            entity_lower = entity.lower()
            # 完整匹配整个实体
            if re.search(r'\b' + re.escape(entity_lower) + r'\b', text):
                return True

        # 如果有关键词，检查是否匹配至少2个关键词
        if key_words:
            matches = sum(1 for w in key_words if w in text)
            if matches >= 2:
                return True

        return False

    # 2. 没有完整实体时，检查关键词匹配
    if key_words:
        matches = sum(1 for w in key_words if w in text)
        return matches >= 2

    # 3. 默认返回 True
    return True


def web_search(query: str, count: int = 5, full_entities: Set[str] = None, key_words: Set[str] = None, topic: str = "") -> List[Dict[str, str]]:
    """网页搜索 - 支持英文搜索与相关性过滤

    Args:
        query: 搜索关键词（建议使用英文）
        count: 返回结果数量，默认 5
        full_entities: 完整实体集合（用于相关性过滤）
        key_words: 关键词集合（用于相关性过滤）
        topic: 原始研究主题（用于相关性过滤）

    Returns:
        包含真实 title, url, snippet 的字典列表
    """
    if not DDGS_AVAILABLE:
        logger.error("搜索库未安装，无法进行搜索")
        return []

    # 如果没有传入实体，从主题中提取
    if (full_entities is None or full_entities == set()) and topic:
        full_entities, key_words = extract_key_entities(topic)

    try:
        ddgs = DDGS(timeout=20)
        results = []
        added_titles = set()

        for r in ddgs.text(query, max_results=count * 2):
            title = r.get("title", "").strip()
            url = r.get("href", "").strip()
            snippet = r.get("body", "").strip()

            if not (title and url and snippet):
                continue
            if title in added_titles:
                continue
            added_titles.add(title)

            result = {"title": title, "url": url, "snippet": snippet}

            # 语义相关性过滤（噪声剔除）
            key_entities = (full_entities or set()) | (key_words or set())
            is_relevant, reject_reason = filter_relevance(result, topic, key_entities)

            if not is_relevant:
                logger.debug(f"过滤掉无关结果: {title[:30]}... (原因: {reject_reason})")
                continue

            # 原有实体相关性检查
            if (full_entities and full_entities != set()) or (key_words and key_words != set()):
                if not is_relevant_old(result, full_entities or set(), key_words or set(), topic):
                    continue

            results.append(result)

            if len(results) >= count:
                break

        logger.info(f"搜索「{query}」返回 {len(results)} 条（过滤后）")
        return results

    except Exception as e:
        logger.error(f"搜索「{query}」失败: {e}")
        return []


def is_english_query(query: str) -> bool:
    """判断查询是否应该使用英文"""
    english_chars = len(re.findall(r'[a-zA-Z]', query))
    total_chars = len(re.findall(r'[a-zA-Z一-鿿]', query))

    if total_chars == 0:
        return False

    if re.search(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', query):
        return True

    return english_chars / total_chars > 0.3


if __name__ == "__main__":
    print("=== 测试实体提取 ===")
    topic = "Henry Ford America First Committee"
    full, keywords = extract_key_entities(topic)
    print(f"完整实体: {full}")
    print(f"关键词: {keywords}")

    print("\n=== 测试相关性过滤 ===")
    test_results = [
        {"title": "Henry Ford - Wikipedia", "url": "https://en.wikipedia.org/wiki/Henry_Ford", "snippet": "Henry Ford was an American industrialist and founder of the Ford Motor Company"},
        {"title": "Thierry Henry - Footballer", "url": "https://en.wikipedia.org/wiki/Thierry_Henry", "snippet": "Thierry Henry is a French former professional footballer"},
        {"title": "Henry Schein - Medical Supply", "url": "https://www.henryschein.com", "snippet": "Henry Schein is a US-based distributor of medical supplies"},
    ]

    for r in test_results:
        relevant = is_relevant(r, full, keywords, topic)
        print(f"  {'✓' if relevant else '✗'} {r['title']}")

    print("\n=== 测试搜索 ===")
    results = web_search("Henry Ford America First Committee", count=3)
    print(f"获取到 {len(results)} 条结果")