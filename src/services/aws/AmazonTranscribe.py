"""
Gladia-driven entrypoint (replaces AWS Transcribe usage).

This script polls the configured queue (SQS) for S3 object-created
notifications and uses the GladiaTranscriber to process audio files.

It preserves the previous behavior of reading SQS messages and updating
the DynamoDB `transcribed` flag, but delegates transcription to Gladia.io.
"""

import logging
import os
import json
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from services.aws.GladiaTranscribe import GladiaTranscriber
from dotenv import load_dotenv

try:
    import boto3
except Exception:
    boto3 = None

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

if boto3 is None:
    logger.error("boto3 is required to poll SQS. Install boto3 or run the Gladia worker script instead.")
    raise SystemExit(1)

sqs = boto3.client(
    "sqs",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)


def main():
    sqs_url = os.getenv("SQS_QUEUE_URL")
    if not sqs_url:
        logger.error("SQS_QUEUE_URL environment variable is not set. Set it or run src/services/aws/gladia_sqs_worker.py")
        return

    transcriber = GladiaTranscriber()

    logger.info(f"Starting Gladia-driven transcription loop. SQS URL: {sqs_url}")

    while True:
        try:
            response = sqs.receive_message(QueueUrl=sqs_url, MaxNumberOfMessages=1, WaitTimeSeconds=10)
            messages = response.get("Messages", [])
            if not messages:
                logger.debug("No messages in queue. Waiting...")
                continue

            message = messages[0]
            logger.info(f"Received message: {message['MessageId']}")
            body = json.loads(message.get("Body", "{}"))

            s3_bucket = body.get("detail", {}).get("bucket", {}).get("name")
            s3_key = body.get("detail", {}).get("object", {}).get("key")
            if not s3_bucket or not s3_key:
                logger.error(f"S3 path or bucket not found in message: {body}")
                sqs.delete_message(QueueUrl=sqs_url, ReceiptHandle=message["ReceiptHandle"])
                continue

            file_id = os.path.splitext(os.path.basename(s3_key))[0]
            logger.info(f"Processing audio: s3://{s3_bucket}/{s3_key} (id={file_id})")

            try:
                success = transcriber.process_transcription(s3_bucket, s3_key, file_id)
                if success:
                    logger.info(f"Successfully processed: {file_id}")
                else:
                    logger.error(f"Failed to process: {file_id}")
            except Exception as e:
                logger.error(f"Error processing transcription for {file_id}: {e}")

            # Delete message regardless to avoid reprocessing; adjust if you want retries
            sqs.delete_message(QueueUrl=sqs_url, ReceiptHandle=message["ReceiptHandle"])

        except KeyboardInterrupt:
            logger.info("Interrupted by user, shutting down")
            break
        except Exception as e:
            logger.error(f"Unexpected error in loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
