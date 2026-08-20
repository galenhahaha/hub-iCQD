import torch
from sentence_transformers import SentenceTransformer

query = "我今天很开心"
data = ["我喜欢机器学习", "我喜欢深度学习", "我今天心情很不错"]

model = SentenceTransformer('./bert-base-chinese')
instruction = "为这个句子生成表示以用于检索相关文章："
query_embedding = model.encode(
    instruction + query,
    convert_to_tensor=True
)
data_embeddings = model.encode(
    [instruction + d for d in data],
    convert_to_tensor=True
)

similarity_scores = torch.nn.functional.cosine_similarity(query_embedding.unsqueeze(0), data_embeddings)

results = sorted(zip(data, similarity_scores.tolist()), key=lambda x: x[1], reverse=True)
for text, score in results:
    print(f"{score:.4f}  {text}")