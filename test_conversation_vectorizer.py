"""
Test script for ConversationVectorizer
"""

import os
import sys

# Add src directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
from core.conversation_vectorizer import ConversationVectorizer


def main():
    """Test ConversationVectorizer functionality"""
    load_dotenv()

    print("🧪 Testing ConversationVectorizer...")

    # Get authentication info from environment variables
    zilliz_uri = os.getenv("ZILLIZ_URI")
    zilliz_token = os.getenv("ZILLIZ_TOKEN")

    if not zilliz_uri or not zilliz_token:
        print("❌ ZILLIZ_URI or ZILLIZ_TOKEN not found in environment")
        return

    try:
        # Initialize vectorizer
        print("🔧 Initializing ConversationVectorizer...")
        vectorizer = ConversationVectorizer(
            zilliz_uri,
            zilliz_token,
            chunk_size=200,
            chunk_overlap=40,
        )

        # Test with sample data
        sample_texts = [
            "これは日本語のテストテキストです。自然言語処理について学習しています。",
            "機械学習とベクトル検索の組み合わせは非常に強力です。ハイブリッド検索を実装します。",
            "対話型AIシステムの開発について説明します。ユーザーとの自然な会話を目指します。",
        ]

        print("📝 Processing sample texts...")
        for i, text in enumerate(sample_texts):
            chunks = vectorizer.process_monologue(text, f"sample_{i+1}.txt")
            print(f"✅ Processed sample {i+1}: {len(chunks)} chunks created")

        # Test searches
        print("\n🔍 Testing hybrid search...")
        try:
            hybrid_results = vectorizer.hybrid_search("機械学習", limit=3)
            print(f"✅ Hybrid search returned {len(hybrid_results)} results")
            for i, result in enumerate(hybrid_results, 1):
                print(f"  {i}. {result.text[:60]}... (Score: {result.score:.3f})")
        except Exception as e:
            print(f"❌ Hybrid search failed: {e}")

        print("\n🔍 Testing dense search...")
        try:
            dense_results = vectorizer.search_similar("自然言語処理", limit=3)
            print(f"✅ Dense search returned {len(dense_results)} results")
            for i, result in enumerate(dense_results, 1):
                print(f"  {i}. {result.text[:60]}... (Score: {result.score:.3f})")
        except Exception as e:
            print(f"❌ Dense search failed: {e}")

        # Show stats
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
            print(f"⚠️ Could not get stats: {e}")

        print("\n🎉 ConversationVectorizer test completed!")

    except Exception as e:
        print(f"❌ An error occurred: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
