"""
Vector generation utilities for conversation embeddings
"""

import sys
import numpy as np
from typing import List

# torch.compile() raises RuntimeError on Python 3.14+ (unsupported), but
# ModernBERT-based models (e.g. cl-nagoya/ruri-v3-*) apply @torch.compile as a
# class-level decorator at import time, so merely importing transformers'
# modernbert module crashes on 3.14+ even though we never need the JIT here.
# Patch torch.compile to a no-op decorator before any such import.
if sys.version_info >= (3, 14):
    import torch

    def _noop_compile(fn=None, *args, **kwargs):
        return fn if fn is not None else (lambda f: f)

    torch.compile = _noop_compile

from sentence_transformers import SentenceTransformer


class DenseVectorGenerator:
    """Dense vector generator using SentenceTransformer"""

    def __init__(
        self,
        model_name: str = "sonoisa/sentence-bert-base-ja-mean-tokens-v2",
        query_prefix: str = "",
        document_prefix: str = "",
    ):
        """
        Initialize dense vector generator
        Args:
            model_name: SentenceTransformer model name
            query_prefix: Prefix prepended to text encoded via generate_query_embedding
                          (e.g. "検索クエリ: " for ruri-v3's asymmetric retrieval format)
            document_prefix: Prefix prepended to text encoded via generate
                              (e.g. "検索文書: " for ruri-v3)
        """
        self.model_name = model_name
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix

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
        prefixed_texts = (
            [self.document_prefix + t for t in texts] if self.document_prefix else texts
        )
        embeddings = self.model.encode(prefixed_texts)

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
        prefixed_query = self.query_prefix + query if self.query_prefix else query
        embedding = self.model.encode([prefixed_query])
        embedding = embedding / np.linalg.norm(embedding, axis=1, keepdims=True)
        return embedding


class HybridVectorGenerator:
    """Generates dense embeddings; sparse (BM25) vectors are derived server-side by Zilliz"""

    def __init__(
        self,
        dense_model: str = "sonoisa/sentence-bert-base-ja-mean-tokens-v2",
        tokenizer=None,
        dense_query_prefix: str = "",
        dense_document_prefix: str = "",
    ):
        """
        Initialize hybrid vector generator
        Args:
            dense_model: SentenceTransformer model name
            tokenizer: Text tokenizer for preprocessing
            dense_query_prefix: Prefix for query-side dense encoding (see DenseVectorGenerator)
            dense_document_prefix: Prefix for document-side dense encoding
        """
        self.dense_generator = DenseVectorGenerator(
            dense_model,
            query_prefix=dense_query_prefix,
            document_prefix=dense_document_prefix,
        )
        self.tokenizer = tokenizer
        print("✅ Initialized hybrid vector generator")
