from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer("../models/BAAI/bge-small-zh-v1.5/") # 没有暴露tokenizer、 model

corpus  = [
    "我喜欢机器学习", # 768 512
    "我喜欢深度学习",
    "我今天心情很不错"
]

query = "我今天很开心"

# 知识库向量
corpus_embeddings = model.encode(corpus, convert_to_tensor=True)

# 查询向量
query_embedding = model.encode(query, convert_to_tensor=True)

cos_scores = util.cos_sim(query_embedding, corpus_embeddings)[0]

# 把相似度和文本打包，从高到低排序
results = sorted(
    zip(corpus, cos_scores),
    key=lambda x: x[1],
    reverse=True
)

# ========= 6. 打印检索结果 =========
print(f"【查询文本】：{query}\n")
for text, score in results:
    print(f"相似度：{score:.4f} | 文本：{text}")