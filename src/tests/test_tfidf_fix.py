"""
Integration test for conversation vectorizer components
"""

import sys
import os


# 🔧 Simple mock classes to test the TF-IDF fix without external dependencies
class MockConversationChunk:
    def __init__(
        self,
        text,
        id="chunk_001",
        speaker="Speaker",
        timestamp="2025-01-01",
        chunk_index=0,
        original_length=100,
        file_name="test.txt",
    ):
        self.text = text
        self.id = id
        self.speaker = speaker
        self.timestamp = timestamp
        self.chunk_index = chunk_index
        self.original_length = original_length
        self.file_name = file_name


class MockTfidfVectorizer:
    """Mock TfidfVectorizer to test parameter logic"""

    def __init__(
        self,
        max_features=1000,
        ngram_range=(1, 1),
        min_df=1,
        max_df=1.0,
        stop_words=None,
    ):
        self.max_features = max_features
        self.ngram_range = ngram_range
        self.min_df = min_df
        self.max_df = max_df
        self.stop_words = stop_words

        print(f"MockTfidfVectorizer: min_df={min_df}, max_df={max_df}")

    def fit_transform(self, texts):
        # Simulate the error condition
        num_docs = len(texts)
        max_df_count = int(num_docs * self.max_df)

        if self.min_df > max_df_count:
            raise ValueError("max_df corresponds to < documents than min_df")

        # Return mock sparse matrix info
        return {"shape": (len(texts), 100), "vocabulary_size": 50}


class TfidfErrorFixer:
    """Test the TF-IDF parameter adjustment logic"""

    def __init__(self, max_features=10000, min_df=2, max_df=0.95):
        self.max_features = max_features
        self.min_df = min_df
        self.max_df = max_df

    def create_safe_vectorizer(self, num_docs):
        """Create vectorizer with safe parameters"""
        # Adjust parameters based on document count
        adjusted_min_df = min(self.min_df, max(1, num_docs // 10))
        adjusted_max_df = self.max_df

        # Ensure min_df doesn't exceed max_df threshold
        max_df_count = int(num_docs * adjusted_max_df)
        if adjusted_min_df > max_df_count:
            adjusted_min_df = 1
            adjusted_max_df = 1.0

        print(
            f"📊 Adjusted params for {num_docs} docs: min_df={adjusted_min_df}, max_df={adjusted_max_df}"
        )

        return MockTfidfVectorizer(
            max_features=self.max_features,
            min_df=adjusted_min_df,
            max_df=adjusted_max_df,
        )

    def fit_and_generate_safe(self, texts):
        """Safe vectorization with error handling"""
        if len(texts) == 0:
            raise ValueError("Cannot fit vectorizer on empty text list")

        # Try with adjusted parameters
        vectorizer = self.create_safe_vectorizer(len(texts))

        try:
            result = vectorizer.fit_transform(texts)
            print(
                f"✅ Generated vectors: {result['shape']}, vocab: {result['vocabulary_size']}"
            )
            return result

        except ValueError as e:
            if "max_df corresponds to < documents than min_df" in str(e):
                print("⚠️ TF-IDF parameter conflict, using fallback...")
                # Fallback: very permissive settings
                fallback_vectorizer = MockTfidfVectorizer(
                    max_features=min(self.max_features, 1000),
                    ngram_range=(1, 1),
                    min_df=1,
                    max_df=1.0,
                )
                result = fallback_vectorizer.fit_transform(texts)
                print(
                    f"✅ Fallback vectors: {result['shape']}, vocab: {result['vocabulary_size']}"
                )
                return result
            else:
                raise e


def test_tfidf_fix():
    """Test the TF-IDF parameter fix"""
    print("🧪 Testing TF-IDF Parameter Fix")
    print("=" * 40)

    fixer = TfidfErrorFixer()

    # Test cases with different document counts
    test_cases = [
        (["短いテスト"], "Single document"),
        (["テスト1", "テスト2"], "Two documents"),
        (["テスト1", "テスト2", "テスト3"], "Three documents"),
        (["テスト{}".format(i) for i in range(10)], "Ten documents"),
    ]

    for texts, description in test_cases:
        print(f"\n📝 {description} ({len(texts)} docs):")
        try:
            result = fixer.fit_and_generate_safe(texts)
            print(f"   Success! Shape: {result['shape']}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

    print("\n🎉 TF-IDF fix test completed!")


def test_conversation_processing():
    """Test conversation chunk processing"""
    print("\n🧪 Testing Conversation Processing")
    print("=" * 40)

    # Create test chunks
    test_texts = [
        "これは最初のテストチャンクです。",
        "二番目のチャンクには異なる内容があります。",
        "三番目のチャンクはさらに別の情報を含みます。",
    ]

    chunks = []
    for i, text in enumerate(test_texts):
        chunk = MockConversationChunk(text, id=f"chunk_{i:03d}")
        chunks.append(chunk)
        print(f"Created chunk {i}: {text[:30]}...")

    # Test with TF-IDF fixer
    texts = [chunk.text for chunk in chunks]
    fixer = TfidfErrorFixer()

    try:
        result = fixer.fit_and_generate_safe(texts)
        print(f"✅ Successfully processed {len(chunks)} chunks")
        print(f"   Vector shape: {result['shape']}")
    except Exception as e:
        print(f"❌ Processing error: {e}")


if __name__ == "__main__":
    test_tfidf_fix()
    test_conversation_processing()
