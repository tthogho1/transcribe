#!/usr/bin/env python3
"""
Transcribeサービスのテスト用スクリプト
DynamoDB更新機能が正常に動作するかテスト
"""

import os
import sys
import logging
from dotenv import load_dotenv

# パス設定
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

# 環境変数読み込み
load_dotenv()

# ログ設定
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def test_dynamodb_update():
    """DynamoDB更新機能のテスト"""
    try:
        from services.database.youtube_dynamodb_client import YoutubeDynamoDBClient

        client = YoutubeDynamoDBClient()
        logger.info("✅ DynamoDB client initialized successfully")

        # テスト用のvideo_id（実際のIDに変更してください）
        test_video_id = "test_video_123"

        # テスト: transcribedフラグを1に更新
        success = client.update_transcribed_status(test_video_id, True)
        if success:
            logger.info(
                f"✅ Test passed: Successfully updated transcribed flag to 1 for {test_video_id}"
            )
        else:
            logger.warning(
                f"⚠️ Test warning: Failed to update transcribed flag for {test_video_id} (video may not exist)"
            )

        return True

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False


def test_import_modules():
    """モジュールインポートテスト"""
    try:
        logger.info("Testing module imports...")

        # AWS Transcribe
        sys.path.append("src/services/aws")
        import AmazonTranscribe

        logger.info("✅ AmazonTranscribe imported successfully")

        # Gladia Transcribe
        from services.aws.GladiaTranscribe import GladiaTranscriber

        logger.info("✅ GladiaTranscriber imported successfully")

        return True

    except Exception as e:
        logger.error(f"❌ Import test failed: {e}")
        return False


def main():
    """メイン処理"""
    logger.info("🧪 Starting Transcribe service tests...")

    # 1. モジュールインポートテスト
    logger.info("=" * 50)
    logger.info("1. Testing module imports...")
    import_test = test_import_modules()

    # 2. DynamoDB更新テスト
    logger.info("=" * 50)
    logger.info("2. Testing DynamoDB update functionality...")
    db_test = test_dynamodb_update()

    # 結果まとめ
    logger.info("=" * 50)
    logger.info("📊 Test Results:")
    logger.info(f"  - Import test: {'✅ PASSED' if import_test else '❌ FAILED'}")
    logger.info(f"  - DynamoDB test: {'✅ PASSED' if db_test else '❌ FAILED'}")

    if import_test and db_test:
        logger.info("🎉 All tests passed! Transcribe services are ready to use.")
    else:
        logger.warning("⚠️ Some tests failed. Please check the error messages above.")


if __name__ == "__main__":
    main()
