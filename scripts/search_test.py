"""
Search-only script for ConversationVectorizer
Initializes the vectorizer and performs a BM25 hybrid search
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

        # Test search
        print("\n🔍 BM25 Hybrid Search test:")
        try:
            hybrid_results = vectorizer.hybrid_search_bm25(query, limit=3)
            if hybrid_results:
                for i, result in enumerate(hybrid_results, 1):
                    print(
                        f"{i}. [{result.search_type}] {result.text[:100]}... (Score: {result.score:.3f})"
                    )
            else:
                print("  No results found")
        except Exception as e:
            print(f"  ❌ Hybrid search failed: {e}")

        # Show vectorizer stats
        print("\n📊 Vectorizer Stats:")
        try:
            stats = vectorizer.get_stats()
            print(
                f"Collection entities: {stats['bm25_stats'].get('num_entities', 'Unknown')}"
            )
            print(
                f"Chunk size: {stats['text_processor']['chunk_size']}"
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
