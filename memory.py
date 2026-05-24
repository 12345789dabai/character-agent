import json
import re
from datetime import datetime
import chromadb
from chromadb.utils import embedding_functions


class MemoryStore:
    """长期记忆存储，基于 ChromaDB 向量数据库"""

    def __init__(self, db_path: str, character_name: str):
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.client = chromadb.PersistentClient(path=db_path)
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', character_name) or 'default'
        self.collection_name = f"memories_{safe_name}"

        try:
            self.collection = self.client.get_collection(
                self.collection_name, embedding_function=self.embedding_fn
            )
        except Exception:
            self.collection = self.client.create_collection(
                self.collection_name, embedding_function=self.embedding_fn
            )

    def add_memory(self, summary: str, facts: list[str], topics: list[str], supersedes: str | None = None):
        """存入一条记忆，supersedes 表示覆盖了哪条旧记忆的 ID"""
        now = datetime.now()
        memory_id = f"mem_{now.strftime('%Y%m%d_%H%M%S_%f')}"
        metadata = {
            "timestamp": now.isoformat(),
            "summary": summary,
            "facts": json.dumps(facts, ensure_ascii=False),
            "topics": json.dumps(topics, ensure_ascii=False),
        }
        if supersedes:
            metadata["supersedes"] = supersedes
            # 同时标记旧记忆
            self.collection.update(
                ids=[supersedes],
                metadatas=[{"superseded_by": memory_id}],
            )
        search_text = summary + " " + " ".join(facts)
        self.collection.add(documents=[search_text], metadatas=[metadata], ids=[memory_id])

    def search(self, query: str, n_results: int = 3, threshold: float | None = None) -> list[dict]:
        """语义搜索，threshold 过滤低分（距离越小越相似）"""
        if self.collection.count() == 0:
            return []

        include = ["metadatas", "distances"]
        results = self.collection.query(
            query_texts=[query], n_results=n_results * 2, include=include
        )
        memories = []
        if results["documents"] and results["documents"][0]:
            for i, meta in enumerate(results["metadatas"][0]):
                dist = results["distances"][0][i] if results.get("distances") else 0
                if threshold is not None and dist > threshold:
                    continue
                memories.append({
                    "timestamp": meta["timestamp"],
                    "summary": meta["summary"],
                    "facts": json.loads(meta["facts"]),
                    "topics": json.loads(meta["topics"]),
                    "distance": dist,
                    "superseded": bool(meta.get("superseded_by")),
                })
                if len(memories) >= n_results:
                    break
        return memories

    def search_with_ids(self, query: str, n_results: int = 3) -> list[dict]:
        """搜索并返回 ID（供后台任务使用）"""
        if self.collection.count() == 0:
            return []

        results = self.collection.query(query_texts=[query], n_results=n_results)
        memories = []
        if results["documents"] and results["documents"][0]:
            for i, mem_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i]
                memories.append({
                    "id": mem_id,
                    "timestamp": meta["timestamp"],
                    "summary": meta["summary"],
                    "facts": json.loads(meta.get("facts", "[]")),
                })
        return memories

    def get_all(self, limit: int = 50) -> list[dict]:
        """获取所有记忆（按时间倒序）"""
        results = self.collection.get(limit=limit)
        memories = []
        if results.get("metadatas"):
            pairs = list(zip(results["ids"], results["metadatas"]))
            pairs.sort(key=lambda x: x[1].get("timestamp", ""), reverse=True)
            for mid, meta in pairs:
                memories.append({
                    "id": mid,
                    "timestamp": meta.get("timestamp", ""),
                    "summary": meta.get("summary", ""),
                    "facts": json.loads(meta.get("facts", "[]")),
                    "topics": json.loads(meta.get("topics", "[]")),
                    "superseded": bool(meta.get("superseded_by")),
                })
        return memories

    def has_similar(self, text: str, threshold: float = 0.4) -> bool:
        if self.collection.count() == 0:
            return False
        results = self.collection.query(
            query_texts=[text], n_results=1, include=["distances"]
        )
        if results.get("distances") and results["distances"][0]:
            return results["distances"][0][0] < threshold
        return False

    def update_memory(self, memory_id: str, summary: str, facts: list[str], topics: list[str]):
        search_text = summary + " " + " ".join(facts)
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "facts": json.dumps(facts, ensure_ascii=False),
            "topics": json.dumps(topics, ensure_ascii=False),
        }
        self.collection.update(ids=[memory_id], documents=[search_text], metadatas=[metadata])

    def delete_memory(self, memory_id: str):
        self.collection.delete(ids=[memory_id])

    def count(self) -> int:
        return self.collection.count()
