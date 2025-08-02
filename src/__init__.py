"""
Conversation vectorization package for hybrid search with Zilliz Cloud
"""

from .conversation_chunk import ConversationChunk, SearchResult, EmbeddingResult
from .text_processor import TextProcessor, JapaneseTokenizer, TextChunker
from .vector_generator import (
    HybridVectorGenerator,
    DenseVectorGenerator,
    SparseVectorGenerator,
)
from .zilliz_client import ZillizClient
from .conversation_vectorizer import ConversationVectorizer

__version__ = "1.0.0"
__author__ = "Transcribe Team"

__all__ = [
    # Main classes
    "ConversationVectorizer",
    # Data classes
    "ConversationChunk",
    "SearchResult",
    "EmbeddingResult",
    # Text processing
    "TextProcessor",
    "JapaneseTokenizer",
    "TextChunker",
    # Vector generation
    "HybridVectorGenerator",
    "DenseVectorGenerator",
    "SparseVectorGenerator",
    # Database client
    "ZillizClient",
]
