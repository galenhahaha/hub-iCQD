# -*- coding: utf-8 -*-
"""使用 BGE 模型做文本语义检索（纯向量余弦相似度，不使用 ES）"""
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_DIR = r"a:\八斗学院Agent_Project\week05作业\work1\BAAI\bge-small-zh-v1.5"

# 待检索文本
QUERY = "我今天很开心"

# 数据库文本
CORPUS = [
    "我喜欢机器学习",
    "我喜欢深度学习",
    "我今天心情很不错",
]

# BGE 官方建议：检索任务中 query 需加指令前缀，语料不加
# QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


def main():
    # 从本地目录加载模型
    model = SentenceTransformer(MODEL_DIR)

    # 编码（normalize 后点积即余弦相似度）
    corpus_emb = model.encode(CORPUS, normalize_embeddings=True)
    query_emb = model.encode(QUERY, normalize_embeddings=True)

    # 余弦相似度：语料向量与 query 向量做点积
    sims = corpus_emb @ query_emb

    print(f"待检索文本: {QUERY}")
    print("检索结果（按相似度降序）:")
    for rank, idx in enumerate(np.argsort(-sims), start=1):
        print(f"  Top{rank}: 相似度={sims[idx]:.4f} | {CORPUS[idx]}")


if __name__ == "__main__":
    main()
