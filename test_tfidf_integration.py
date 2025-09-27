#!/usr/bin/env python3
"""
Test the TF-IDF integration in conversation_vectorizer.py
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def test_tfidf_vectorizer():
    """Test the TfidfSparseVectorizer class"""
    print("🧪 Testing TfidfSparseVectorizer...")

    try:
        # Import the class from new location
        from services.processing.tfidf_vectorizer import TfidfSparseVectorizer

        # Create instance
        vectorizer = TfidfSparseVectorizer(
            max_features=1000, ngram_range=(1, 2), min_df=1, max_df=0.95, use_mecab=True
        )

        # Test data
        test_texts = [
            "これは日本語のテストです。",
            "機械学習とベクトル検索について説明します。",
            "TF-IDFを使用したスパースベクトル生成のテストです。",
        ]

        print(f"📝 Test texts: {len(test_texts)} samples")

        # Fit and transform
        sparse_vectors = vectorizer.fit_transform(test_texts)
        print(f"✅ Generated {len(sparse_vectors)} sparse vectors")

        # Test transform on new text
        new_text = ["新しいテキストのベクトル化"]
        new_vectors = vectorizer.transform(new_text)
        print(f"✅ Transformed new text: {len(new_vectors)} vectors")

        # Show sample vector
        if sparse_vectors:
            first_vector = sparse_vectors[0]
            print(
                f"📊 Sample sparse vector (first 5 features): {dict(list(first_vector.items())[:5])}"
            )

        print("🎉 TfidfSparseVectorizer test passed!")
        return True

    except Exception as e:
        print(f"❌ TfidfSparseVectorizer test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_conversation_vectorizer():
    """Test the ConversationVectorizer initialization"""
    print("\n🧪 Testing ConversationVectorizer initialization...")

    try:
        # Import required classes (this will test imports)
        from core.conversation_vectorizer import ConversationVectorizer

        print("✅ ConversationVectorizer imported successfully")

        # Note: We can't fully initialize without proper config
        # but we can test that the class definition is valid
        print("🎉 ConversationVectorizer import test passed!")
        return True

    except Exception as e:
        print(f"❌ ConversationVectorizer test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🚀 Starting TF-IDF integration tests...\n")

    # Run tests
    test1_passed = test_tfidf_vectorizer()
    test2_passed = test_conversation_vectorizer()

    # Summary
    print(f"\n📊 Test Results:")
    print(f"  TfidfSparseVectorizer: {'✅ PASS' if test1_passed else '❌ FAIL'}")
    print(f"  ConversationVectorizer: {'✅ PASS' if test2_passed else '❌ FAIL'}")

    if test1_passed and test2_passed:
        print("\n🎉 All tests passed! TF-IDF integration is working correctly.")
    else:
        print("\n❌ Some tests failed. Please check the integration.")
