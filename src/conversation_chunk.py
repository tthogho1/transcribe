"""
Data classes for conversation processing
"""

from dataclasses import dataclass
from typing import Dict, Any, List


@dataclass
class ConversationChunk:
    """Data class for conversation chunks"""

    id: str
    text: str
    speaker: str
    timestamp: str
    chunk_index: int
    original_length: int
    file_name: str


@dataclass
class SearchResult:
    """Data class for search results"""

    text: str
    speaker: str
    timestamp: str
    file_name: str
    score: float
    search_type: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "text": self.text,
            "speaker": self.speaker,
            "timestamp": self.timestamp,
            "file_name": self.file_name,
            "score": self.score,
            "search_type": self.search_type,
        }


@dataclass
class EmbeddingResult:
    """Data class for embedding generation results"""

    dense_embeddings: Any  # np.ndarray
    sparse_embeddings: List[Dict[int, float]]

    @property
    def count(self) -> int:
        """Number of embeddings generated"""
        return len(self.dense_embeddings) if self.dense_embeddings is not None else 0
