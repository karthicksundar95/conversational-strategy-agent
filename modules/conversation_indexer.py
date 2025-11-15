"""
Conversation Indexer - Vector indexing for historical conversations
Indexes conversations after completion for semantic search.
"""

import json
import os
import faiss
import numpy as np
import requests
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# Embedding configuration (same as document indexing)
EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"

# Storage paths
ROOT = Path(__file__).parent.parent.resolve()
INDEX_FILE = ROOT / "historical_conversation_index.bin"
METADATA_FILE = ROOT / "historical_conversation_store.json"


def get_embedding(text: str) -> np.ndarray:
    """Get embedding vector for text using Ollama."""
    try:
        result = requests.post(EMBED_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=10)
        result.raise_for_status()
        return np.array(result.json()["embedding"], dtype=np.float32)
    except Exception as e:
        # Fallback: return zero vector if embedding fails
        print(f"[conversation_indexer] Warning: Embedding failed: {e}")
        return np.zeros(768, dtype=np.float32)  # nomic-embed-text dimension


class ConversationIndexer:
    """Manages vector indexing of historical conversations."""
    
    def __init__(self):
        self.index: Optional[faiss.Index] = None
        self.metadata: List[Dict] = []
        self.load_index()
    
    def load_index(self):
        """Load existing index and metadata."""
        try:
            if INDEX_FILE.exists():
                self.index = faiss.read_index(str(INDEX_FILE))
                print(f"[conversation_indexer] Loaded existing index with {self.index.ntotal} conversations")
            else:
                self.index = None
                print("[conversation_indexer] No existing index found, will create new one")
            
            if METADATA_FILE.exists():
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
            else:
                self.metadata = []
        except Exception as e:
            print(f"[conversation_indexer] Error loading index: {e}")
            self.index = None
            self.metadata = []
    
    def save_index(self):
        """Save index and metadata to disk."""
        try:
            if self.index is not None:
                os.makedirs(INDEX_FILE.parent, exist_ok=True)
                faiss.write_index(self.index, str(INDEX_FILE))
            
            os.makedirs(METADATA_FILE.parent, exist_ok=True)
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=2)
            
            print(f"[conversation_indexer] Saved index with {len(self.metadata)} conversations")
        except Exception as e:
            print(f"[conversation_indexer] Error saving index: {e}")
    
    def index_conversation(
        self,
        session_id: str,
        user_query: str,
        final_answer: str,
        tool_calls: Optional[List[Dict]] = None,
        timestamp: Optional[float] = None
    ):
        """
        Index a completed conversation.
        
        Args:
            session_id: Unique session identifier
            user_query: Original user query
            final_answer: Final answer provided
            tool_calls: List of tool calls made (optional)
            timestamp: Conversation timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now().timestamp()
        
        # Create searchable text (query + answer for semantic search)
        searchable_text = f"{user_query}\n{final_answer}"
        if tool_calls:
            tool_summary = ", ".join([tc.get("tool_name", "") for tc in tool_calls])
            searchable_text += f"\nTools used: {tool_summary}"
        
        try:
            # Get embedding
            embedding = get_embedding(searchable_text)
            
            # Initialize index if needed
            if self.index is None:
                dim = len(embedding)
                self.index = faiss.IndexFlatL2(dim)
                print(f"[conversation_indexer] Created new index with dimension {dim}")
            
            # Add to index
            self.index.add(embedding.reshape(1, -1))
            
            # Store metadata
            metadata_entry = {
                "session_id": session_id,
                "user_query": user_query,
                "final_answer": final_answer,
                "tool_calls": tool_calls or [],
                "timestamp": timestamp,
                "index_position": len(self.metadata)  # Position in index
            }
            self.metadata.append(metadata_entry)
            
            # Save immediately (Option 1: on-the-fly indexing)
            self.save_index()
            
            print(f"[conversation_indexer] ✅ Indexed conversation: {session_id[:20]}...")
            
        except Exception as e:
            print(f"[conversation_indexer] ❌ Error indexing conversation: {e}")
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Search historical conversations using semantic similarity.
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of conversation metadata matching the query
        """
        if self.index is None or self.index.ntotal == 0:
            return []
        
        try:
            # Get query embedding
            query_embedding = get_embedding(query).reshape(1, -1)
            
            # Search index
            distances, indices = self.index.search(query_embedding, min(top_k, self.index.ntotal))
            
            # Retrieve metadata for matched conversations
            results = []
            for i, idx in enumerate(indices[0]):
                if idx < len(self.metadata):
                    result = self.metadata[idx].copy()
                    result["similarity_distance"] = float(distances[0][i])
                    results.append(result)
            
            return results
            
        except Exception as e:
            print(f"[conversation_indexer] Error searching conversations: {e}")
            return []
    
    def get_conversation_count(self) -> int:
        """Get total number of indexed conversations."""
        if self.index is None:
            return 0
        return self.index.ntotal


# Global instance
_conversation_indexer: Optional[ConversationIndexer] = None


def get_indexer() -> ConversationIndexer:
    """Get or create global conversation indexer instance."""
    global _conversation_indexer
    if _conversation_indexer is None:
        _conversation_indexer = ConversationIndexer()
    return _conversation_indexer


def index_conversation(
    session_id: str,
    user_query: str,
    final_answer: str,
    tool_calls: Optional[List[Dict]] = None,
    timestamp: Optional[float] = None
):
    """Convenience function to index a conversation."""
    indexer = get_indexer()
    indexer.index_conversation(session_id, user_query, final_answer, tool_calls, timestamp)


def search_conversations(query: str, top_k: int = 5) -> List[Dict]:
    """Convenience function to search conversations."""
    indexer = get_indexer()
    return indexer.search(query, top_k)

