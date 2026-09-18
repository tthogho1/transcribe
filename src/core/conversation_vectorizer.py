"""
Main conversation vectorizer orchestrating all components
"""

import os
import sys
import numpy as np
from typing import List, Dict

# Add src directory to Python path when running as standalone script
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(current_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

from models.conversation_chunk import ConversationChunk, SearchResult
from services.processing.text_processor import TextProcessor
from services.processing.vector_generator import HybridVectorGenerator
from services.database.zilliz_bm25_client import ZillizBM25Client
from services.data.extract_text_fromS3 import S3JsonTextExtractor

from dotenv import load_dotenv, find_dotenv

# Load .env from project root (robust in various run contexts)
load_dotenv(find_dotenv(usecwd=True))


class ConversationVectorizer:
    """Main conversation vectorizer orchestrating all components"""

    def __init__(
        self,
        zilliz_uri: str,
        zilliz_token: str,
        embedding_model: str = "cl-nagoya/ruri-v3-310m",
        chunk_size: int = 300,
        chunk_overlap: int = 50,
        bm25_collection_name: str = "conversation_chunks_bm25",
        dense_query_prefix: str = "検索クエリ: ",
        dense_document_prefix: str = "検索文書: ",
    ):
        """
        Initialize conversation vectorizer
        Args:
            zilliz_uri: Zilliz Cloud URI
            zilliz_token: Zilliz Cloud token
            embedding_model: SentenceTransformer model name. Defaults to ruri-v3-310m
                              (768D, matches the existing dense_vector schema).
            chunk_size: Chunk size in characters
            chunk_overlap: Overlap size in characters
            bm25_collection_name: Zilliz collection name (dense + native BM25 sparse)
            dense_query_prefix / dense_document_prefix: ruri-v3 uses asymmetric
                              retrieval prefixes ("1+3 prefix scheme"); pass "" for
                              models that don't use them.
        """
        # Initialize components
        print("🔧 Initializing TextProcessor...")
        self.text_processor = TextProcessor(chunk_size, chunk_overlap)
        print("✅ TextProcessor initialized")

        print("🔧 Initializing HybridVectorGenerator...")
        self.vector_generator = HybridVectorGenerator(
            dense_model=embedding_model,
            tokenizer=self.text_processor,
            dense_query_prefix=dense_query_prefix,
            dense_document_prefix=dense_document_prefix,
        )
        print("✅ HybridVectorGenerator initialized")

        print("🔧 Initializing ZillizBM25Client...")
        if zilliz_uri:
            try:
                self.bm25_client = ZillizBM25Client(
                    zilliz_uri, zilliz_token, bm25_collection_name
                )
                print("✅ ZillizBM25Client initialized")
            except Exception as e:
                print(f"⚠️ ZillizBM25Client initialization failed: {e}")
                self.bm25_client = None
        else:
            print("⚠️ ZILLIZ_URI not provided - skipping ZillizBM25Client initialization")
            self.bm25_client = None

        print("✅ ConversationVectorizer initialized with all components")

    def process_monologue_bm25(
        self, text: str, file_name: str
    ) -> List[ConversationChunk]:
        """
        Complete processing pipeline for monologue text.
        Only dense embeddings are computed client-side; the sparse vector is
        derived automatically by Zilliz's BM25 function from the chunk text.
        Args:
            text: Monologue text
            file_name: Name of the file being processed
        Returns:
            List of processed chunks
        """
        print("🔄 Starting BM25 monologue processing...")

        chunks = self.text_processor.process_text(text, file_name)

        dense_embeddings = self.vector_generator.dense_generator.generate(
            [chunk.text for chunk in chunks]
        )

        if self.bm25_client:
            try:
                self.bm25_client.insert_data(chunks, dense_embeddings)
            except Exception as e:
                print(f"⚠️ Skipped inserting data into BM25 collection: {e}")
        else:
            print("⚠️ BM25 client not available - skipping data insertion")

        print("🎉 BM25 processing completed!")
        return chunks

    def hybrid_search_bm25(
        self, query: str, limit: int = 5, rerank_k: int = 100
    ) -> List[SearchResult]:
        """
        Perform hybrid search using the native-BM25 collection: dense ANN
        combined server-side with BM25 full-text search on the raw query text.
        Args:
            query: Search query
            limit: Number of final results
            rerank_k: Number of candidates considered per side before fusion
        Returns:
            List of search results
        """
        try:
            if not self.bm25_client:
                print("⚠️ BM25 client not available - hybrid BM25 search unavailable")
                return []

            dense_query = (
                self.vector_generator.dense_generator.generate_query_embedding(query)
            )

            return self.bm25_client.hybrid_search(dense_query, query, limit, rerank_k)

        except Exception as e:
            print(f"❌ BM25 hybrid search error: {e}")
            return []

    def get_stats(self) -> Dict:
        """
        Get vectorizer statistics
        Returns:
            Dictionary containing statistics
        """
        return {
            "bm25_stats": self.bm25_client.get_collection_stats() if self.bm25_client else {},
            "text_processor": {
                "chunk_size": self.text_processor.chunker.chunk_size,
                "chunk_overlap": self.text_processor.chunker.chunk_overlap,
            },
            "vector_generator": {
                "dense_model": self.vector_generator.dense_generator.model_name,
            },
        }


# Main function for testing and usage example
def main():
    """Main function for testing the vectorizer"""
    extractor = S3JsonTextExtractor()

    bucket_name = os.getenv("S3_BUCKET_NAME")
    json_files = extractor.list_json_files_in_bucket(bucket_name)

    # Get authentication info from environment variables
    zilliz_uri = os.getenv("ZILLIZ_URI", "your-zilliz-uri")
    zilliz_token = os.getenv("ZILLIZ_TOKEN", "your-zilliz-token")

    try:
        # Initialize vectorizer with detailed debugging
        print("🔧 Initializing ConversationVectorizer...")

        print("🔧 Step 1: Creating ConversationVectorizer instance...")
        vectorizer = ConversationVectorizer(
            zilliz_uri,
            zilliz_token,
            chunk_size=200,
            chunk_overlap=40,
        )
        print("✅ ConversationVectorizer initialized successfully!")

        # Process files
        for json_file_key in json_files:
            print(f"\nProcessing file: {json_file_key}")

            # Extract text from JSON file
            result = extractor.extract_text_from_s3_json(bucket_name, json_file_key)
            sample_monologue = result["extracted_texts"][0]["text"]

            # Process monologue
            chunks = vectorizer.process_monologue_bm25(sample_monologue, json_file_key)

        # Test search
        print("\n🔍 BM25 Hybrid Search test:")
        hybrid_results = vectorizer.hybrid_search_bm25("仕事の楽しみ方", limit=3)
        for i, result in enumerate(hybrid_results, 1):
            print(
                f"{i}. [{result.search_type}] {result.text[:100]}... (Score: {result.score:.3f})"
            )

        # Show stats
        print("\n📊 Vectorizer Stats:")
        stats = vectorizer.get_stats()
        print(
            f"Collection entities: {stats['bm25_stats'].get('num_entities', 'Unknown')}"
        )
        print(f"Chunk size: {stats['text_processor']['chunk_size']}")

    except Exception as e:
        print(f"❌ An error occurred: {e}")


if __name__ == "__main__":
    main()
