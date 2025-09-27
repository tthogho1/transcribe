"""
Vector generation utilities for conversation embeddings
"""

import numpy as np
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer

from models.conversation_chunk import ConversationChunk, EmbeddingResult

# Note: JapaneseSparseVectorizer functionality moved to TfidfSparseVectorizer in conversation_vectorizer.py


class DenseVectorGenerator:
    """Dense vector generator using SentenceTransformer"""

    def __init__(
        self, model_name: str = "sonoisa/sentence-bert-base-ja-mean-tokens-v2"
    ):
        """
        Initialize dense vector generator
        Args:
            model_name: SentenceTransformer model name
        """
        self.model_name = model_name

        # Pre-configure fugashi with unidic to avoid unidic_lite dependency
        try:
            import fugashi
            import unidic

            # Pre-initialize fugashi with unidic to prevent automatic unidic_lite detection
            _ = fugashi.Tagger()
            print("✅ Pre-configured fugashi with unidic")
        except ImportError:
            print("⚠️ fugashi/unidic not available")
        except Exception as fugashi_error:
            print(f"⚠️ fugashi pre-configuration failed: {fugashi_error}")

        # Temporarily disable any potential MeCab dependencies
        import os

        os.environ["DISABLE_TOKENIZERS_PARALLELISM"] = "true"

        try:
            self.model = SentenceTransformer(model_name)
            print(f"✅ Loaded SentenceTransformer model: {model_name}")
        except Exception as e:
            print(f"❌ Failed to load SentenceTransformer: {e}")
            # Fallback to a simpler model or raise the error
            raise e

    def generate(self, texts: List[str]) -> np.ndarray:
        """
        Generate dense embeddings for texts
        Args:
            texts: List of text strings
        Returns:
            Dense embeddings (L2 normalized)
        """
        embeddings = self.model.encode(texts)

        # Apply L2 normalization for cosine similarity
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        print(f"✅ Generated {len(texts)} dense embeddings")
        return embeddings

    def generate_query_embedding(self, query: str) -> np.ndarray:
        """
        Generate embedding for a single query
        Args:
            query: Query text
        Returns:
            Query embedding (L2 normalized)
        """
        embedding = self.model.encode([query])
        embedding = embedding / np.linalg.norm(embedding, axis=1, keepdims=True)
        return embedding


class SparseVectorGenerator:
    """Sparse vector generator using JapaneseSparseVectorizer"""

    def __init__(self):
        """
        Initialize sparse vector generator (disabled)
        """
        print("⚠️ SparseVectorGenerator disabled - using TfidfSparseVectorizer instead")
        self.vectorizer = None
        self.is_fitted = False

    # BM25関数使用時は不要なメソッドは削除

    def fit_and_generate(self, texts: List[str]) -> List[Dict[int, float]]:
        """
        Disabled - sparse vectors handled by TfidfSparseVectorizer
        """
        print("⚠️ SparseVectorGenerator disabled - returning empty sparse vectors")
        return []

    def generate(self, texts: List[str]) -> List[Dict[int, float]]:
        """
        Disabled - sparse vectors handled by TfidfSparseVectorizer
        """
        print("⚠️ SparseVectorGenerator disabled - returning empty sparse vectors")
        return []

    def generate_query_vector(self, query: str) -> Dict[int, float]:
        """
        Disabled - sparse vectors handled by TfidfSparseVectorizer
        """
        print("⚠️ SparseVectorGenerator disabled - returning empty sparse vector")
        return {}


class HybridVectorGenerator:
    """Hybrid vector generator combining dense and sparse vectors"""

    def __init__(
        self,
        dense_model: str = "sonoisa/sentence-bert-base-ja-mean-tokens-v2",
        tokenizer=None,
        **sparse_kwargs,
    ):
        """
        Initialize hybrid vector generator
        Args:
            dense_model: SentenceTransformer model name
            tokenizer: Text tokenizer for preprocessing
            **sparse_kwargs: Additional arguments for sparse vectorizer
        """
        self.dense_generator = DenseVectorGenerator(dense_model)
        self.sparse_generator = SparseVectorGenerator(**sparse_kwargs)
        self.tokenizer = tokenizer
        print("✅ Initialized hybrid vector generator")

    def preprocess_texts(self, texts: List[str]) -> List[str]:
        """
        Preprocess texts using tokenizer if available
        Args:
            texts: List of text strings
        Returns:
            Preprocessed texts
        """
        if self.tokenizer:
            return [self.tokenizer.tokenize_text(text) for text in texts]
        return texts

    def generate_embeddings(self, chunks: List[ConversationChunk]) -> EmbeddingResult:
        """
        Generate both dense and sparse embeddings for chunks
        Args:
            chunks: List of conversation chunks
        Returns:
            EmbeddingResult containing both types of embeddings
        """
        texts = [chunk.text for chunk in chunks]

        # Generate dense embeddings
        dense_embeddings = self.dense_generator.generate(texts)

        # Preprocess texts for sparse vectors (BM25 function will handle sparse generation)
        # preprocessed_texts = self.preprocess_texts(texts)
        preprocessed_texts = texts

        # Generate sparse embeddings (BM25 function handles this automatically)
        sparse_embeddings = self.sparse_generator.fit_and_generate(preprocessed_texts)

        print(f"✅ Generated hybrid embeddings for {len(chunks)} chunks")
        return EmbeddingResult(dense_embeddings, sparse_embeddings)

    def generate_query_embeddings(
        self, query: str
    ) -> Tuple[np.ndarray, Dict[int, float]]:
        """
        Generate both dense and sparse embeddings for a query
        Args:
            query: Query text
        Returns:
            Tuple of (dense_embedding, sparse_embedding_dict)
        """
        # Generate dense query embedding
        dense_query = self.dense_generator.generate_query_embedding(query)

        # Generate sparse query embedding for BM25 search
        sparse_query = self.sparse_generator.generate_query_vector(query)

        return dense_query, sparse_query
        # return dense_query
