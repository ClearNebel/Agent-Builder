import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import os

MODEL = None
INDEX = None
DOCUMENTS = None
INDEX_PATH = os.path.join(os.path.dirname(__file__), '../models/rag_index/document.index')
DOC_PATH = os.path.join(os.path.dirname(__file__), '../data/knowledge_base.txt')


def _load_rag_dependencies():
    """Loads the RAG model, index, and documents into memory."""
    global MODEL, INDEX, DOCUMENTS
    if MODEL is None:
        print("[RAG Handler] Loading SentenceTransformer model...")
        MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    if INDEX is None and os.path.exists(INDEX_PATH):
        print(f"[RAG Handler] Loading FAISS index from {INDEX_PATH}...")
        INDEX = faiss.read_index(INDEX_PATH)
    if DOCUMENTS is None and os.path.exists(DOC_PATH):
        print(f"[RAG Handler] Loading documents from {DOC_PATH}...")
        with open(DOC_PATH, 'r', encoding='utf-8') as f:
            DOCUMENTS = [line.strip() for line in f.readlines() if line.strip()]

def query_knowledge_base(query: str, k: int = 3) -> str:
    """
    Searches the knowledge base for information relevant to the query.
    Use this to answer questions about specific topics covered in our documents,
    like 'Quantum Computing', 'Photosynthesis', or 'Mitochondria'.
    :param query: The question or topic to search for.
    :param k: The number of relevant documents to return.
    """
    _load_rag_dependencies()

    if INDEX is None or DOCUMENTS is None or MODEL is None:
        return "Error: RAG index is not built or dependencies are missing. Please run `python rag/build_index.py` first."

    print(f"[RAG Handler] Searching for: '{query}'")
    query_embedding = MODEL.encode([query])
    distances, indices = INDEX.search(np.array(query_embedding).astype('float32'), k)
    
    results = [DOCUMENTS[i] for i in indices[0]]
    
    if not results:
        return "No relevant information found in the knowledge base."
        
    return "Relevant information from knowledge base:\n" + "\n---\n".join(results)