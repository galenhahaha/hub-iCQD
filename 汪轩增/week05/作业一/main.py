import os
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim

# ---------- 1. 配置 ----------
# 模型在本地磁盘上的路径（由 modelscope download 得到）
MODEL_DIR = r"C:\Users\19916\.cache\modelscope\models\google-bert--bert-base-chinese\snapshots\master"

# 待检索的查询句
QUERY = "我今天很开心"

# 数据库文本（语料库）
CORPUS = [
    "我喜欢机器学习",
    "我喜欢深度学习",
    "我今天心情很不错",
]


def ensure_model(model_dir: str) -> str:
    if os.path.isdir(model_dir) and os.path.exists(os.path.join(model_dir, "config.json")):
        return model_dir
    print(f"[info] 本地未找到模型 {model_dir}，尝试自动下载...")
    from modelscope import snapshot_download
    return snapshot_download(model_id="BAAI/bge-small-zh-v1.5", local_dir=model_dir)


def main():
    model_dir = ensure_model(MODEL_DIR)
    print(f"[info] 加载模型: {model_dir}")
    model = SentenceTransformer(model_dir)

    # BGE 系列建议：查询句加上检索指令前缀，能显著提升召回效果
    query_instruction = "为这个句子生成表示以用于检索相关文章："

    # bge-small-zh-v1.5 推荐对 Embedding 做归一化（normalize_embeddings=True）
    query_emb = model.encode(
        query_instruction + QUERY,
        normalize_embeddings=True,
    )
    corpus_emb = model.encode(
        CORPUS,
        normalize_embeddings=True,
    )

    # 计算余弦相似度并排序（cos_sim 已因归一化等价于内积）
    similarities = cos_sim(query_emb, corpus_emb)[0]
    ranked = sorted(
        zip(CORPUS, similarities.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )

    print("\n========== 检索结果 ==========")
    print(f"查询：{QUERY}\n")
    for rank, (text, score) in enumerate(ranked, 1):
        print(f"Top{rank}  ({score:.4f})  {text}")


if __name__ == "__main__":
    main()