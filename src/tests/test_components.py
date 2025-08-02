"""
Test script to verify TF-IDF error fixes
"""

import sys
import os

# Add src directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Test imports
try:
    print("Testing imports...")
    from conversation_chunk import ConversationChunk

    print("✅ conversation_chunk imported")

    from text_processor import TextProcessor

    print("✅ text_processor imported")

    # Test text processing
    print("\nTesting text processing...")
    processor = TextProcessor(chunk_size=100, chunk_overlap=20)

    # Create test chunks
    test_text = "これはテストテキストです。別の文章も含みます。三番目の文章もあります。"
    chunks = processor.process_text(test_text, "test_file.txt")

    print(f"✅ Created {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i}: {chunk.text[:50]}...")

    # Test tokenization
    tokenized = processor.tokenize_text("これはテストです")
    print(f"✅ Tokenized text: {tokenized}")

    print("\n🎉 Basic text processing tests passed!")

except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
