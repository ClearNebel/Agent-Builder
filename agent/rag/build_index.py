import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import os

def build_and_save_index():
    """Reads documents, creates embeddings, and saves a FAISS index."""
    doc_path = os.path.join(os.path.dirname(__file__), '../data/knowledge_base.txt')
    index_path = os.path.join(os.path.dirname(__file__), '../models/rag_index/document.index')
    
    if not os.path.exists(doc_path):
        print(f"Error: Knowledge base file not found at {doc_path}")
        return

    print("Loading documents...")
    with open(doc_path, 'r', encoding='utf-8') as f:
        documents = [line.strip() for line in f.readlines() if line.strip()]

    print("Loading sentence-transformer model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    print("Encoding documents... (This may take a while)")
    embeddings = model.encode(documents, show_progress_bar=True)
    embeddings = np.array(embeddings).astype('float32')
    
    print("Building FAISS index...")
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    faiss.write_index(index, index_path)
    
    print(f"Successfully built and saved index for {len(documents)} documents to {index_path}")

if __name__ == "__main__":
    build_and_save_index()