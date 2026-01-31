"""Top-level package exports for the project.

This module re-exports commonly used classes from the internal
subpackages so tests and external scripts can `import src` safely.
"""

from .models.conversation_chunk import ConversationChunk, SearchResult, EmbeddingResult
from .services.processing.text_processor import TextProcessor, JapaneseTokenizer, TextChunker
from .core.conversation_vectorizer import ConversationVectorizer

__version__ = "1.0.0"
__author__ = "Transcribe Team"

__all__ = [
    "ConversationVectorizer",
    "ConversationChunk",
    "SearchResult",
    "EmbeddingResult",
    "TextProcessor",
    "JapaneseTokenizer",
    "TextChunker",
]
