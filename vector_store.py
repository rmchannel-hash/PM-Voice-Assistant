import chromadb
from sentence_transformers import SentenceTransformer

class PMOVectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path="./data/chroma")
        self.collection = self.client.get_or_create_collection("pmo_docs")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')

    def add_document(self, doc_id, text, metadata=None):
        emb = self.model.encode(text).tolist()

        self.collection.add(
            ids=[doc_id],
            embeddings=[emb],
            documents=[text],
            metadatas=[metadata or {}]
        )

    def search(self, query, top_k=5):
        emb = self.model.encode(query).tolist()

        return self.collection.query(
            query_embeddings=[emb],
            n_results=top_k
        )