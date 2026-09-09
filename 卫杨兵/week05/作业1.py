from sentence_transformers import SentenceTransformer
import numpy as np

# 数据库文本
corpus = [
    "我喜欢机器学习",
    "我喜欢深度学习",
    "我今天心情很不错"

]
# 待检索的文本
query = "我今天很开心"

model = SentenceTransformer("BAAI/bge-small-zh-v1.5/")  # sentence-bert 微调之后的
corpus_embeddings = model.encode(corpus)
query_embedding = model.encode(query)

similarities = model.similarity([query_embedding], corpus_embeddings)[0]  # 计算余弦相似度
print(similarities)

top_indices = np.argsort(similarities)  # 按相似度排序

print(f"查询文本: {query}\n")
print("检索结果:")
for i, idx in enumerate(top_indices, 1):
    print(f"{i}. {corpus[idx]} (相似度: {similarities[idx]:.4f})")
