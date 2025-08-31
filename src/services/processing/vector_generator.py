"""
Vector generation utilities for conversation embeddings
"""

import numpy as np
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer

# BM25関数使用時はTF-IDF不要
# from sklearn.feature_extraction.text import TfidfVectorizer
# import scipy.sparse as sp

from models.conversation_chunk import ConversationChunk, EmbeddingResult


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
    """Sparse vector generator for BM25 function"""

    def __init__(self):
        """
        Initialize sparse vector generator for BM25 function
        For data insertion, we generate sparse vectors manually
        For search queries, BM25 function handles it automatically
        """
        print("✅ Initialized BM25 function sparse vector generator")

        # For data insertion, we need TF-IDF vectorizer
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self.vectorizer = TfidfVectorizer(
                max_features=10000,
                ngram_range=(1, 2),
                min_df=1,
                max_df=1.0,
                stop_words=None,
            )
            self.is_fitted = False
            print("✅ TF-IDF vectorizer initialized for data insertion")
        except ImportError:
            print("⚠️ sklearn not available, sparse vector generation limited")
            self.vectorizer = None

        # For query processing, we still need basic TF-IDF capabilities
        try:
            self.query_vectorizer = TfidfVectorizer(
                max_features=10000,
                ngram_range=(1, 2),
                min_df=1,
                max_df=1.0,
                stop_words=None,
            )
            self.query_vectorizer_fitted = False
            print("✅ Query vectorizer initialized for BM25 search")
        except ImportError:
            print("⚠️ sklearn not available, query processing limited")
            self.query_vectorizer = None

    # BM25関数使用時は不要なメソッドは削除

    def fit_and_generate(self, texts: List[str]) -> List[Dict[int, float]]:
        """
        Generate sparse vectors for data insertion
        BM25 function will be used for search, but we need manual sparse vectors for insertion
        Args:
            texts: List of text strings
        Returns:
            List of sparse vectors in Zilliz format
        """
        if self.vectorizer is None:
            print("⚠️ TF-IDF vectorizer not available, returning empty sparse vectors")
            return []

        try:
            # Fit vectorizer if not fitted
            if not self.is_fitted:
                self.vectorizer.fit(texts)
                self.is_fitted = True
                print("✅ TF-IDF vectorizer fitted on data")

            # Generate sparse vectors
            sparse_matrix = self.vectorizer.transform(texts)

            # Convert to Zilliz sparse vector format
            sparse_vectors = []
            for i in range(sparse_matrix.shape[0]):
                row = sparse_matrix.getrow(i)
                indices = row.indices
                data = row.data
                sparse_dict = {int(idx): float(val) for idx, val in zip(indices, data)}
                sparse_vectors.append(sparse_dict)

            print(f"✅ Generated {len(sparse_vectors)} sparse vectors for data insertion")
            return sparse_vectors

        except Exception as e:
            print(f"❌ Sparse vector generation error: {e}")
            return []

    def generate(self, texts: List[str]) -> List[Dict[int, float]]:
        """
        Generate sparse vectors for texts (assumes vectorizer is already fitted)
        Args:
            texts: List of text strings
        Returns:
            List of sparse vectors in Zilliz format
        """
        if self.vectorizer is None or not self.is_fitted:
            print("⚠️ TF-IDF vectorizer not fitted, returning empty sparse vectors")
            return []

        try:
            # Generate sparse vectors
            sparse_matrix = self.vectorizer.transform(texts)

            # Convert to Zilliz sparse vector format
            sparse_vectors = []
            for i in range(sparse_matrix.shape[0]):
                row = sparse_matrix.getrow(i)
                indices = row.indices
                data = row.data
                sparse_dict = {int(idx): float(val) for idx, val in zip(indices, data)}
                sparse_vectors.append(sparse_dict)

            return sparse_vectors

        except Exception as e:
            print(f"❌ Sparse vector generation error: {e}")
            return []

    def generate_query_vector(self, query: str) -> Dict[int, float]:
        """
        Generate sparse vector for BM25 search query
        Args:
            query: Query text
        Returns:
            Sparse vector in Zilliz format
        """
        if self.query_vectorizer is None:
            raise ValueError("Query vectorizer not available")

        # Fit vectorizer if not fitted
        if not self.query_vectorizer_fitted:
            # Use basic vocabulary for fitting
            basic_vocab = [
                "です",
                "ます",
                "ました",
                "します",
                "する",
                "した",
                "できる",
                "あります",
            ]
            self.query_vectorizer.fit(basic_vocab)
            self.query_vectorizer_fitted = True

        # Generate sparse vector for query
        query_matrix = self.query_vectorizer.transform([query])

        # Convert to Zilliz sparse vector format
        sparse_vectors = []
        for i in range(query_matrix.shape[0]):
            row = query_matrix.getrow(i)
            indices = row.indices
            data = row.data
            sparse_dict = {int(idx): float(val) for idx, val in zip(indices, data)}
            sparse_vectors.append(sparse_dict)

        return sparse_vectors[0] if sparse_vectors else {}

    # BM25関数使用時は不要
    # @staticmethod
    # def sparse_matrix_to_dict(sparse_matrix: sp.csr_matrix) -> List[Dict[int, float]]:
    #     """
    #     Convert scipy sparse matrix to Zilliz sparse vector format
    #     Args:
    #         sparse_matrix: Scipy sparse matrix
    #     Returns:
    #     List of sparse vectors in Zilliz format
    #     """
    #     sparse_vectors = []

    #     for i in range(sparse_matrix.shape[0]):
    #         row = sparse_matrix.getrow(i)
    #         indices = row.indices
    #         data = row.data

    #         # Zilliz sparse vector format: {index: value}
    #         sparse_dict = {int(idx): float(val) for idx, val in zip(indices, data)}
    #         sparse_vectors.append(sparse_dict)

    #     return sparse_vectors


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
        preprocessed_texts = self.preprocess_texts(texts)

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
