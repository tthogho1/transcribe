"""
Vector generation utilities for conversation embeddings
"""

import numpy as np
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
import scipy.sparse as sp

from .conversation_chunk import ConversationChunk, EmbeddingResult


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
        self.model = SentenceTransformer(model_name)
        print(f"✅ Loaded SentenceTransformer model: {model_name}")

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
    """Sparse vector generator using TF-IDF"""

    def __init__(
        self,
        max_features: int = 10000,
        ngram_range: Tuple[int, int] = (1, 2),
        min_df: int = 1,
        max_df: float = 0.95,
    ):
        """
        Initialize sparse vector generator
        Args:
            max_features: Maximum number of features
            ngram_range: N-gram range for feature extraction
            min_df: Minimum document frequency
            max_df: Maximum document frequency
        """
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.min_df = min_df
        self.max_df = max_df
        self.vectorizer = None
        self.is_fitted = False
        print(
            f"✅ Initialized TF-IDF vectorizer parameters (max_features={max_features})"
        )

    def _create_vectorizer(self, num_docs: int) -> TfidfVectorizer:
        """
        Create TF-IDF vectorizer with parameters adjusted for document count
        Args:
            num_docs: Number of documents
        Returns:
            Configured TfidfVectorizer
        """
        # Adjust parameters based on document count
        adjusted_min_df = min(self.min_df, max(1, num_docs // 10))
        adjusted_max_df = self.max_df

        # Ensure min_df doesn't exceed max_df threshold
        max_df_count = int(num_docs * adjusted_max_df)
        if adjusted_min_df > max_df_count:
            adjusted_min_df = 1
            adjusted_max_df = 1.0

        print(
            f"📊 TF-IDF params: docs={num_docs}, min_df={adjusted_min_df}, max_df={adjusted_max_df}"
        )

        return TfidfVectorizer(
            max_features=self.max_features,
            ngram_range=self.ngram_range,
            min_df=adjusted_min_df,
            max_df=adjusted_max_df,
            stop_words=None,
        )

    def fit_and_generate(self, texts: List[str]) -> sp.csr_matrix:
        """
        Fit vectorizer and generate sparse vectors
        Args:
            texts: List of text strings
        Returns:
            Sparse matrix
        """
        if len(texts) == 0:
            raise ValueError("Cannot fit vectorizer on empty text list")

        # Create vectorizer with adjusted parameters
        self.vectorizer = self._create_vectorizer(len(texts))

        try:
            sparse_vectors = self.vectorizer.fit_transform(texts)
            self.is_fitted = True

            print(f"✅ Generated sparse vectors: {sparse_vectors.shape}")
            print(f"   Vocabulary size: {len(self.vectorizer.vocabulary_)}")
            return sparse_vectors

        except ValueError as e:
            if "max_df corresponds to < documents than min_df" in str(e):
                print("⚠️ TF-IDF parameter conflict, using fallback settings...")
                # Fallback: very permissive settings
                self.vectorizer = TfidfVectorizer(
                    max_features=min(self.max_features, 1000),
                    ngram_range=(1, 1),  # Only unigrams
                    min_df=1,
                    max_df=1.0,  # Include all documents
                    stop_words=None,
                )
                sparse_vectors = self.vectorizer.fit_transform(texts)
                self.is_fitted = True

                print(f"✅ Generated sparse vectors (fallback): {sparse_vectors.shape}")
                return sparse_vectors
            else:
                raise e

    def generate(self, texts: List[str]) -> sp.csr_matrix:
        """
        Generate sparse vectors (vectorizer must be fitted)
        Args:
            texts: List of text strings
        Returns:
            Sparse matrix
        """
        if not self.is_fitted:
            raise ValueError("Vectorizer must be fitted first")

        sparse_vectors = self.vectorizer.transform(texts)
        return sparse_vectors

    def generate_query_vector(self, query: str) -> sp.csr_matrix:
        """
        Generate sparse vector for a single query
        Args:
            query: Query text
        Returns:
            Sparse query vector
        """
        if not self.is_fitted:
            raise ValueError("Vectorizer must be fitted first")

        return self.vectorizer.transform([query])

    @staticmethod
    def sparse_matrix_to_dict(sparse_matrix: sp.csr_matrix) -> List[Dict[int, float]]:
        """
        Convert scipy sparse matrix to Zilliz sparse vector format
        Args:
            sparse_matrix: Scipy sparse matrix
        Returns:
            List of sparse vectors in Zilliz format
        """
        sparse_vectors = []

        for i in range(sparse_matrix.shape[0]):
            row = sparse_matrix.getrow(i)
            indices = row.indices
            data = row.data

            # Zilliz sparse vector format: {index: value}
            sparse_dict = {int(idx): float(val) for idx, val in zip(indices, data)}
            sparse_vectors.append(sparse_dict)

        return sparse_vectors


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

        # Preprocess texts for sparse vectors
        preprocessed_texts = self.preprocess_texts(texts)

        # Generate sparse embeddings
        sparse_matrix = self.sparse_generator.fit_and_generate(preprocessed_texts)
        sparse_embeddings = self.sparse_generator.sparse_matrix_to_dict(sparse_matrix)

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
            Tuple of (dense_embedding, sparse_embedding)
        """
        # Generate dense query embedding
        dense_query = self.dense_generator.generate_query_embedding(query)

        # Preprocess query for sparse vector
        preprocessed_query = self.preprocess_texts([query])[0]

        # Generate sparse query embedding
        sparse_query_matrix = self.sparse_generator.generate_query_vector(
            preprocessed_query
        )
        sparse_query = self.sparse_generator.sparse_matrix_to_dict(sparse_query_matrix)[
            0
        ]

        return dense_query, sparse_query
