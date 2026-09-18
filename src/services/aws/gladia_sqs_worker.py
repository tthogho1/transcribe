"""
SQS-driven worker: polls an SQS queue for S3 object-created notifications
and runs Gladia transcription (via GladiaTranscriber) for each message.

This is a push/queue-driven alternative to the DynamoDB-scan-driven
ingestion path used by scripts/gladia_transcribe/ and
scripts/generate_embeddings_with_vectorizer.py.
"""

import json
import logging
import os
import sys
import time

import boto3
from dotenv import load_dotenv

# Add src/ to the path so "services.aws.GladiaTranscribe" resolves when this
# file is run standalone (python src/services/sqs/gladia_sqs_worker.py).
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from services.aws.GladiaTranscribe import GladiaTranscriber

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()


def main():
    """メイン処理：SQSからメッセージを受信してGladia転写を実行"""
    try:
        transcriber = GladiaTranscriber()

        sqs_client = boto3.client(
            "sqs",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION"),
        )

        sqs_queue_url = os.getenv("SQS_QUEUE_URL")
        if not sqs_queue_url:
            raise ValueError("SQS_QUEUE_URL環境変数が設定されていません")

        logger.info(f"🚀 Gladia Transcription Worker started")
        logger.info(f"📋 SQS Queue URL: {sqs_queue_url}")

        # SQSからメッセージを受信してTranscribeを実行
        while True:
            try:
                response = sqs_client.receive_message(
                    QueueUrl=sqs_queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=10
                )

                messages = response.get("Messages", [])
                if not messages:
                    logger.info("⏳ No messages in SQS queue. Waiting...")
                    continue

                message = messages[0]
                logger.info(f"📨 Received message: {message['MessageId']}")

                try:
                    body = json.loads(message["Body"])

                    # S3ファイルパス取得
                    s3_bucket = body.get("detail", {}).get("bucket", {}).get("name")
                    s3_key = body.get("detail", {}).get("object", {}).get("key")

                    if not s3_bucket or not s3_key:
                        logger.error(
                            f"❌ S3 path or bucket not found in SQS message: {body}"
                        )
                        continue

                    file_id = os.path.splitext(os.path.basename(s3_key))[0]
                    logger.info(f"🎵 Processing audio file: s3://{s3_bucket}/{s3_key}")

                    # Gladia転写処理を実行
                    success = transcriber.process_transcription(
                        s3_bucket, s3_key, file_id
                    )

                    if success:
                        logger.info(f"✅ Successfully processed: {file_id}")
                    else:
                        logger.error(f"❌ Failed to process: {file_id}")

                except Exception as e:
                    logger.error(f"❌ Error processing message: {e}")

                finally:
                    # SQSメッセージを削除
                    sqs_client.delete_message(
                        QueueUrl=sqs_queue_url, ReceiptHandle=message["ReceiptHandle"]
                    )
                    logger.info(f"🗑️ Message deleted from SQS")

            except KeyboardInterrupt:
                logger.info("🛑 Interrupted by user. Shutting down...")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected error in main loop: {e}")
                time.sleep(5)  # エラー時は5秒待機

    except Exception as e:
        logger.error(f"❌ Failed to initialize Gladia transcriber: {e}")
        return


if __name__ == "__main__":
    main()
