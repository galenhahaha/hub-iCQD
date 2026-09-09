from typing import Type

from sentence_transformers import SentenceTransformer


model = SentenceTransformer('../../models/BAAI/bge-small-zh-v1.5')


sentences = [
    "我喜欢机器学习",
    "我今天心情很不错",
    "我喜欢深度学习",
    "我今天很不开心"
]
embeddings = model.encode(sentences) # 正向传播 -》 句子编码 （token的编码 -》 mean pooling）
print(embeddings.shape) #（3，512）

text = "我今天很开心"
text_embeddings = model.encode(text)


similarity = model.similarity(embeddings,text_embeddings)
print(similarity)
similarity_numpy = similarity.numpy()
for i in range(similarity_numpy.shape[0]):
    print(f"{sentences[i]} 与 {text} 的余弦相似度为 {similarity_numpy[i]}")
