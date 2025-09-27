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
from services.processing.tfidf_vectorizer import TfidfSparseVectorizer
from services.database.zilliz_client import ZillizClient
from services.data.extract_text_fromS3 import S3JsonTextExtractor

from dotenv import load_dotenv

load_dotenv()


class ConversationVectorizer:
    """Main conversation vectorizer orchestrating all components"""

    def __init__(
        self,
        zilliz_uri: str,
        zilliz_token: str,
        embedding_model: str = "sonoisa/sentence-bert-base-ja-mean-tokens-v2",
        chunk_size: int = 300,
        chunk_overlap: int = 50,
        collection_name: str = "conversation_chunks_hybrid",
    ):
        """
        Initialize conversation vectorizer
        Args:
            zilliz_uri: Zilliz Cloud URI
            zilliz_token: Zilliz Cloud token
            embedding_model: SentenceTransformer model name
            chunk_size: Chunk size in characters
            chunk_overlap: Overlap size in characters
            collection_name: Zilliz collection name
        """
        # Initialize components
        print("🔧 Initializing TextProcessor...")
        self.text_processor = TextProcessor(chunk_size, chunk_overlap)
        print("✅ TextProcessor initialized")

        print("🔧 Initializing HybridVectorGenerator...")
        self.vector_generator = HybridVectorGenerator(
            dense_model=embedding_model, tokenizer=self.text_processor
        )
        print("✅ HybridVectorGenerator initialized")

        print("🔧 Initializing ZillizClient...")
        self.zilliz_client = ZillizClient(zilliz_uri, zilliz_token, collection_name)
        print("✅ ZillizClient initialized")

        # Initialize TF-IDF sparse vectorizer
        print("🔧 Initializing TfidfSparseVectorizer...")
        self.sparse_vectorizer = TfidfSparseVectorizer(
            max_features=10000,
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
            use_mecab=True,  # Re-enable to see detailed error
        )
        print("✅ TfidfSparseVectorizer initialized")

        print("✅ ConversationVectorizer initialized with all components")

    def process_monologue(self, text: str, file_name: str) -> List[ConversationChunk]:
        """
        Complete processing pipeline for monologue text
        Args:
            text: Monologue text
            file_name: Name of the file being processed
        Returns:
            List of processed chunks
        """
        print("🔄 Starting hybrid monologue processing...")

        # 1. Process text into chunks
        chunks = self.text_processor.process_text(text, file_name)

        # 2. Generate dense embeddings
        dense_embeddings = self.vector_generator.dense_generator.generate(
            [chunk.text for chunk in chunks]
        )

        # 3. Generate sparse embeddings using TF-IDF
        texts = [chunk.text for chunk in chunks]
        if not self.sparse_vectorizer.is_fitted:
            sparse_embeddings = self.sparse_vectorizer.fit_transform(texts)
        else:
            sparse_embeddings = self.sparse_vectorizer.transform(texts)

        # 4. Create embeddings result
        from models.conversation_chunk import EmbeddingResult

        embeddings = EmbeddingResult(
            dense_embeddings=dense_embeddings,
            sparse_embeddings=sparse_embeddings,
        )

        # 5. Insert into Zilliz
        self.zilliz_client.insert_data(chunks, embeddings)

        print("🎉 Hybrid processing completed!")
        return chunks

    def hybrid_search(
        self, query: str, limit: int = 5, rerank_k: int = 100
    ) -> List[SearchResult]:
        """
        Perform hybrid search combining dense and sparse vectors
        Args:
            query: Search query
            limit: Number of final results
            rerank_k: Number of candidates for reranking
        Returns:
            List of search results
        """
        try:
            # Generate dense query embedding
            dense_query = (
                self.vector_generator.dense_generator.generate_query_embedding(query)
            )

            # Generate sparse query embedding using TF-IDF
            sparse_query = self.sparse_vectorizer.transform([query])[0]

            # Perform hybrid search
            results = self.zilliz_client.hybrid_search(
                dense_query, sparse_query, limit, rerank_k
            )
            return results

        except Exception as e:
            print(f"❌ Hybrid search error: {e}")
            # Fallback to dense search
            return self.search_similar(query, limit)

    def search_similar(self, query: str, limit: int = 5) -> List[SearchResult]:
        """
        Perform dense vector search (fallback method)
        Args:
            query: Search query
            limit: Number of results to return
        Returns:
            List of search results
        """
        try:
            # Generate dense query embedding only
            dense_query = (
                self.vector_generator.dense_generator.generate_query_embedding(query)
            )

            # Perform dense search
            results = self.zilliz_client.dense_search(dense_query, limit)

            return results

        except Exception as e:
            print(f"❌ Dense search error: {e}")
            return []

    def get_stats(self) -> Dict:
        """
        Get vectorizer statistics
        Returns:
            Dictionary containing statistics
        """
        return {
            "zilliz_stats": self.zilliz_client.get_collection_stats(),
            "text_processor": {
                "chunk_size": self.text_processor.chunker.chunk_size,
                "chunk_overlap": self.text_processor.chunker.chunk_overlap,
                "tokenizer_available": self.text_processor.tokenizer.mecab is not None,
            },
            "vector_generator": {
                "dense_model": self.vector_generator.dense_generator.model_name,
                "sparse_fitted": self.vector_generator.sparse_generator.is_fitted,
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
            chunks = vectorizer.process_monologue(sample_monologue, json_file_key)

        # Test searches
        print("\n🔍 Hybrid Search test:")
        hybrid_results = vectorizer.hybrid_search("仕事の楽しみ方", limit=3)
        for i, result in enumerate(hybrid_results, 1):
            print(
                f"{i}. [{result.search_type}] {result.text[:100]}... (Score: {result.score:.3f})"
            )

        print("\n🔍 Dense Search test:")
        dense_results = vectorizer.search_similar("仕事の楽しみ方", limit=3)
        for i, result in enumerate(dense_results, 1):
            print(
                f"{i}. [{result.search_type}] {result.text[:100]}... (Score: {result.score:.3f})"
            )

        # Show stats
        print("\n📊 Vectorizer Stats:")
        stats = vectorizer.get_stats()
        print(
            f"Collection entities: {stats['zilliz_stats'].get('num_entities', 'Unknown')}"
        )
        print(f"Tokenizer available: {stats['text_processor']['tokenizer_available']}")
        print(f"Sparse vectorizer fitted: {stats['vector_generator']['sparse_fitted']}")

    except Exception as e:
        print(f"❌ An error occurred: {e}")


if __name__ == "__main__":
    main()
