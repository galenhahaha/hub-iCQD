from sentence_transformers import SentenceTransformer

# 加载本地下载的 bge 检索模型（modelscope 下载，184MB）
# bge 系列是专门做语义检索训练的向量模型
model = SentenceTransformer("../models/BAAI/bge-small-zh-v1.5/")

# 待检索的文本（查询）
query = "我今天很开心"

# 数据库文本（候选文档）
documents = [
    "我喜欢机器学习",
    "我喜欢深度学习",
    "我今天心情很不错",
]

# 重要：bge 官方建议查询文本加上检索指令前缀（提升检索效果）
# 文档文本不需要加前缀
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

import torch

query_embedding = torch.tensor(model.encode(QUERY_INSTRUCTION + query, normalize_embeddings=True))
doc_embeddings = torch.tensor(model.encode(documents, normalize_embeddings=True))

# 计算查询与每个文档的余弦相似度（normalize 后点积即余弦相似度）
similarities = torch.mm(query_embedding.unsqueeze(0), doc_embeddings.T).squeeze(0)

# 按相似度从高到低排序
ranked_indices = similarities.argsort(descending=True)

print(f"查询文本: {query}")
print("-" * 50)
for rank, idx in enumerate(ranked_indices, start=1):
    print(f"第 {rank} 名: {documents[idx]}  (相似度: {similarities[idx]:.4f})")
