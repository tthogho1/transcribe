"""
Search-only script for ConversationVectorizer
Initializes the vectorizer and performs hybrid and dense searches
"""

import os
import sys

# Add src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
from core.conversation_vectorizer import ConversationVectorizer


def main():
    """Search-only test for ConversationVectorizer"""
    load_dotenv()

    print("🔍 ConversationVectorizer Search Test")
    print("=" * 50)

    # Get authentication info from environment variables
    zilliz_uri = os.getenv("ZILLIZ_URI", "your-zilliz-uri")
    zilliz_token = os.getenv("ZILLIZ_TOKEN", "your-zilliz-token")

    if zilliz_uri == "your-zilliz-uri" or zilliz_token == "your-zilliz-token":
        print("❌ Please set ZILLIZ_URI and ZILLIZ_TOKEN environment variables")
        return

    query = "殴られたときに誉れでございます。を使いますか？"
    try:
        # Initialize vectorizer
        print("🔧 Initializing ConversationVectorizer...")
        vectorizer = ConversationVectorizer(
            zilliz_uri,
            zilliz_token,
            chunk_size=200,
            chunk_overlap=40,
        )

        # Test searches
        print("\n🔍 Hybrid Search test:")
        try:
            hybrid_results = vectorizer.hybrid_search(query, limit=3)
            if hybrid_results:
                for i, result in enumerate(hybrid_results, 1):
                    print(
                        f"{i}. [{result.search_type}] {result.text[:100]}... (Score: {result.score:.3f})"
                    )
            else:
                print("  No results found")
        except Exception as e:
            print(f"  ❌ Hybrid search failed: {e}")

        print("\n🔍 Dense Search test:")
        try:
            dense_results = vectorizer.search_similar(query, limit=3)
            if dense_results:
                for i, result in enumerate(dense_results, 1):
                    print(
                        f"{i}. [{result.search_type}] {result.text[:100]}... (Score: {result.score:.3f})"
                    )
            else:
                print("  No results found")
        except Exception as e:
            print(f"  ❌ Dense search failed: {e}")

        # --- Sparse-only search (TF-IDF) ---
        print("\n🔍 Sparse (TF-IDF only) Search test:")
        try:
            # Get the sparse vectorizer and Zilliz collection
            sparse_vec = vectorizer.sparse_vectorizer
            col = vectorizer.zilliz_client.collection
            # Transform query to sparse vector
            sparse_query = sparse_vec.transform([query])[0]
            # Prepare search params
            search_params = {"metric_type": "IP", "params": {}}
            # Run search
            results = col.search(
                [sparse_query],
                "sparse_vector",
                search_params,
                limit=3,
                output_fields=["text", "speaker", "timestamp", "file_name"],
            )
            if results and results[0]:
                for i, hit in enumerate(results[0], 1):
                    text = hit.entity.get("text", "")
                    score = hit.score
                    print(f"{i}. [sparse] {text[:100]}... (Score: {score:.3f})")
            else:
                print("  No results found")
        except Exception as e:
            print(f"  ❌ Sparse search failed: {e}")

        # Show vectorizer stats
        print("\n📊 Vectorizer Stats:")
        try:
            stats = vectorizer.get_stats()
            print(
                f"Collection entities: {stats['zilliz_stats'].get('num_entities', 'Unknown')}"
            )
            print(
                f"Tokenizer available: {stats['text_processor']['tokenizer_available']}"
            )
            print(
                f"Sparse vectorizer fitted: {stats['vector_generator']['sparse_fitted']}"
            )
        except Exception as e:
            print(f"  ⚠️ Could not get stats: {e}")

        print("\n🎉 Search test completed!")

    except Exception as e:
        print(f"❌ An error occurred: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
