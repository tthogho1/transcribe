#!/usr/bin/env python3
"""
Test script for add_embedding_attribute.py

使用例とテストケースを含むスクリプト
"""

import os
import sys
import json
from typing import Dict, Any

# パスを追加してメインスクリプトをインポート
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from add_embedding_attribute import DynamoDBEmbeddingUpdater, setup_logging
except ImportError as e:
    print(f"❌ Cannot import main script: {e}")
    sys.exit(1)


def test_environment_variables():
    """環境変数の確認"""
    print("🔍 Environment Variables Check:")

    required_vars = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
    optional_vars = ["AWS_REGION", "DYNAMO_TABLE_NAME"]

    all_good = True

    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"   ✅ {var}: {'*' * len(value[:10])}...")
        else:
            print(f"   ❌ {var}: Not set")
            all_good = False

    for var in optional_vars:
        value = os.getenv(var)
        status = "✅" if value else "⚠️"
        display_value = value if value else "Not set (using default)"
        print(f"   {status} {var}: {display_value}")

    return all_good


def test_connection():
    """DynamoDB接続テスト"""
    print("\n🔗 DynamoDB Connection Test:")

    try:
        table_name = os.getenv("DYNAMO_TABLE_NAME", "YoutubeList")
        region = os.getenv("AWS_REGION", "ap-northeast-1")

        updater = DynamoDBEmbeddingUpdater(table_name, region)
        print(f"   ✅ Successfully connected to table: {table_name}")
        print(f"   ✅ Region: {region}")

        return updater

    except Exception as e:
        print(f"   ❌ Connection failed: {e}")
        return None


def test_scan_sample():
    """サンプルデータスキャンテスト"""
    print("\n📊 Sample Data Scan Test:")

    updater = test_connection()
    if not updater:
        return False

    try:
        # 最初の5件だけスキャン
        response = updater.table.scan(Limit=5)
        items = response.get("Items", [])

        print(f"   📋 Found {len(items)} sample items")

        if items:
            sample_item = items[0]
            print(f"   🔍 Sample item keys: {list(sample_item.keys())}")

            # transcribed属性の確認
            transcribed = sample_item.get("transcribed", "Missing")
            print(f"   🏷️  Sample transcribed value: {transcribed}")

            # embedding属性の確認
            has_embedding = "embedding" in sample_item
            print(f"   🧠 Has embedding attribute: {has_embedding}")

        return True

    except Exception as e:
        print(f"   ❌ Scan test failed: {e}")
        return False


def show_usage_examples():
    """使用例を表示"""
    print("\n📚 Usage Examples:")

    examples = [
        {
            "description": "Basic dry-run test",
            "command": "python scripts/add_embedding_attribute.py --dry-run",
        },
        {
            "description": "Dry-run with custom table",
            "command": "python scripts/add_embedding_attribute.py --table-name MyTable --dry-run",
        },
        {
            "description": "Actual update execution",
            "command": "python scripts/add_embedding_attribute.py",
        },
        {
            "description": "Debug mode with detailed logging",
            "command": "python scripts/add_embedding_attribute.py --log-level DEBUG",
        },
        {
            "description": "Custom region and table",
            "command": "python scripts/add_embedding_attribute.py --region us-east-1 --table-name VideoData",
        },
    ]

    for i, example in enumerate(examples, 1):
        print(f"   {i}. {example['description']}:")
        print(f"      {example['command']}")
        print()


def test_dry_run():
    """ドライランテスト"""
    print("🧪 Running Dry-Run Test:")

    try:
        table_name = os.getenv("DYNAMO_TABLE_NAME", "YoutubeList")
        region = os.getenv("AWS_REGION", "ap-northeast-1")

        updater = DynamoDBEmbeddingUpdater(table_name, region)
        success = updater.run_update(dry_run=True)

        if success:
            print("   ✅ Dry-run completed successfully!")
            return True
        else:
            print("   ❌ Dry-run failed!")
            return False

    except Exception as e:
        print(f"   ❌ Dry-run error: {e}")
        return False


def main():
    """メインテスト実行"""
    print("🧪 DynamoDB Embedding Attribute Updater - Test Suite")
    print("=" * 60)

    # ログ設定
    setup_logging("INFO")

    # 1. 環境変数チェック
    env_ok = test_environment_variables()

    if not env_ok:
        print("\n⚠️ Please set required environment variables:")
        print("   export AWS_ACCESS_KEY_ID='your-access-key'")
        print("   export AWS_SECRET_ACCESS_KEY='your-secret-key'")
        print("   export AWS_REGION='ap-northeast-1'")
        print("   export DYNAMO_TABLE_NAME='YoutubeList'")
        return False

    # 2. 接続テスト
    if not test_connection():
        return False

    # 3. サンプルデータテスト
    if not test_scan_sample():
        return False

    # 4. 使用例表示
    show_usage_examples()

    # 5. ドライランテスト
    if not test_dry_run():
        return False

    print("🎉 All tests passed! The script is ready to use.")
    print("\nNext steps:")
    print("1. Review the dry-run results above")
    print("2. Run the actual update: python scripts/add_embedding_attribute.py")

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        sys.exit(1)
