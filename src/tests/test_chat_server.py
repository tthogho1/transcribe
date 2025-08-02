#!/usr/bin/env python3
"""
Test script for the Chat Server
Tests both the search functionality and OpenAI integration
"""

import os
import sys
import json
import requests
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
CHAT_SERVER_URL = "http://localhost:5000"
TEST_QUERIES = [
    "営業について教えて",
    "AIの活用方法は？",
    "人工知能の課題",
    "機械学習の進歩",
    "技術の発展",
]


def test_health_check():
    """Test the health check endpoint"""
    try:
        print("🔍 Testing health check...")
        response = requests.get(f"{CHAT_SERVER_URL}/health", timeout=10)

        if response.status_code == 200:
            data = response.json()
            print("✅ Health check passed")
            print(f"   Status: {data['status']}")
            print(f"   Zilliz: {data['services']['zilliz']}")
            print(f"   OpenAI: {data['services']['openai']}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False


def test_search_api(query):
    """Test the search API endpoint"""
    try:
        print(f"🔍 Testing search API with query: '{query}'")

        payload = {"query": query, "limit": 3}

        response = requests.post(
            f"{CHAT_SERVER_URL}/api/search", json=payload, timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Search successful - found {len(data['results'])} results")

            for i, result in enumerate(data["results"], 1):
                print(f"   [{i}] Score: {result['score']:.3f}")
                print(f"       Speaker: {result['speaker']}")
                print(f"       Text: {result['text'][:100]}...")
                print()

            return True
        else:
            print(f"❌ Search failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Search error: {e}")
        return False


def test_chat_api(query):
    """Test the chat API endpoint"""
    try:
        print(f"💬 Testing chat API with query: '{query}'")

        payload = {"query": query}

        response = requests.post(
            f"{CHAT_SERVER_URL}/api/chat",
            json=payload,
            timeout=60,  # OpenAI can take longer
        )

        if response.status_code == 200:
            data = response.json()
            print("✅ Chat successful")
            print(f"   Answer: {data['answer'][:200]}...")
            print(f"   Sources: {len(data['sources'])} found")
            print(f"   Tokens used: {data['tokens_used']}")
            print()
            return True
        else:
            print(f"❌ Chat failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Chat error: {e}")
        return False


def wait_for_server(max_attempts=30):
    """Wait for the server to be ready"""
    print("⏳ Waiting for chat server to be ready...")

    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{CHAT_SERVER_URL}/health", timeout=5)
            if response.status_code == 200:
                print("✅ Server is ready!")
                return True
        except:
            pass

        print(f"   Attempt {attempt + 1}/{max_attempts}...")
        time.sleep(2)

    print("❌ Server did not become ready in time")
    return False


def main():
    """Run all tests"""
    print("🚀 Starting Chat Server Tests")
    print("=" * 50)

    # Check if server is running
    if not wait_for_server():
        print("\n❌ Cannot connect to server. Make sure it's running:")
        print("   python src/chat_server.py")
        sys.exit(1)

    # Test health check
    print("\n" + "=" * 50)
    if not test_health_check():
        print("❌ Health check failed - stopping tests")
        sys.exit(1)

    # Test search API
    print("\n" + "=" * 50)
    print("🔍 Testing Search API")
    search_success = 0
    for query in TEST_QUERIES[:2]:  # Test first 2 queries
        if test_search_api(query):
            search_success += 1
        time.sleep(1)  # Rate limiting

    print(f"\n📊 Search API Results: {search_success}/2 successful")

    # Test chat API (if OpenAI is configured)
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and openai_key != "your_openai_api_key_here":
        print("\n" + "=" * 50)
        print("💬 Testing Chat API")
        chat_success = 0
        for query in TEST_QUERIES[:2]:  # Test first 2 queries
            if test_chat_api(query):
                chat_success += 1
            time.sleep(2)  # Rate limiting for OpenAI

        print(f"\n📊 Chat API Results: {chat_success}/2 successful")
    else:
        print("\n⚠️  Skipping Chat API tests - OpenAI API key not configured")

    print("\n" + "=" * 50)
    print("🎉 Test suite completed!")
    print("\n💡 Tips:")
    print("   - Access web interface: http://localhost:5000")
    print("   - Check logs for detailed information")
    print("   - Update OpenAI API key in .env for full functionality")


if __name__ == "__main__":
    main()
