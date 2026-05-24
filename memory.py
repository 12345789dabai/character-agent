import json
from datetime import datetime
import chromadb
from chromadb.utils import embedding_functions


class MemoryStore:
    """长期记忆存储，基于 ChromaDB 向量数据库"""

    def __init__(self, db_path: str, character_name: str):
        # 使用多语言嵌入模型，更好支持中文
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.client = chromadb.PersistentClient(path=db_path)
        # ChromaDB 集合名只允许 ASCII 字母数字和 ._-，去掉中文
        import re
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

    def add_memory(self, summary: str, facts: list[str], topics: list[str]):
        """存入一条记忆"""
        now = datetime.now()
        memory_id = f"mem_{now.strftime('%Y%m%d_%H%M%S_%f')}"
        metadata = {
            "timestamp": now.isoformat(),
            "summary": summary,
            "facts": json.dumps(facts, ensure_ascii=False),
            "topics": json.dumps(topics, ensure_ascii=False),
        }
        # documents 字段用于语义搜索
        search_text = summary + " " + " ".join(facts)
        self.collection.add(documents=[search_text], metadatas=[metadata], ids=[memory_id])

    def search(self, query: str, n_results: int = 3) -> list[dict]:
        """语义搜索相关记忆"""
        if self.collection.count() == 0:
            return []

        results = self.collection.query(query_texts=[query], n_results=n_results)
        memories = []
        if results["documents"] and results["documents"][0]:
            for meta in results["metadatas"][0]:
                memories.append({
                    "timestamp": meta["timestamp"],
                    "summary": meta["summary"],
                    "facts": json.loads(meta["facts"]),
                    "topics": json.loads(meta["topics"]),
                })
        return memories

    def get_all(self, limit: int = 50) -> list[dict]:
        """获取所有记忆（按时间倒序）"""
        results = self.collection.get(limit=limit)
        memories = []
        if results.get("metadatas"):
            # ChromaDB 的 get 返回的 ids 和 metadatas 顺序一致
            pairs = list(zip(results["ids"], results["metadatas"]))
            # 按时间戳倒序
            pairs.sort(key=lambda x: x[1].get("timestamp", ""), reverse=True)
            for mid, meta in pairs:
                memories.append({
                    "id": mid,
                    "timestamp": meta.get("timestamp", ""),
                    "summary": meta.get("summary", ""),
                    "facts": json.loads(meta.get("facts", "[]")),
                    "topics": json.loads(meta.get("topics", "[]")),
                })
        return memories

    def has_similar(self, text: str, threshold: float = 0.4) -> bool:
        """检查是否有相似度过高的已有记忆（用于去重）"""
        if self.collection.count() == 0:
            return False
        results = self.collection.query(
            query_texts=[text], n_results=1, include=["distances"]
        )
        if results.get("distances") and results["distances"][0]:
            return results["distances"][0][0] < threshold
        return False

    def delete_memory(self, memory_id: str):
        """删除一条记忆"""
        self.collection.delete(ids=[memory_id])

    def count(self) -> int:
        return self.collection.count()
