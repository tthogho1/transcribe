import boto3
import logging
import os
import json
from dotenv import load_dotenv
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from services.database.youtube_dynamodb_client import YoutubeDynamoDBClient

# ログ設定
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

sqs = boto3.client(
    "sqs",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)

transcribe = boto3.client(
    "transcribe",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)

# DynamoDBクライアント初期化
dynamodb_client = YoutubeDynamoDBClient()

# SQSからメッセージ受信し、Transcribeジョブを実行
logger.info("SQS URL : " + os.getenv("SQS_QUEUE_URL"))
while True:
    response = sqs.receive_message(
        QueueUrl=os.getenv("SQS_QUEUE_URL"), MaxNumberOfMessages=1, WaitTimeSeconds=10
    )
    messages = response.get("Messages", [])
    if not messages:
        logger.info("No messages in SQS queue. Waiting...")
        continue

    message = messages[0]
    logger.info(f"Received message: {message['MessageId']}")
    body = json.loads(message["Body"])
    # S3ファイルパス取得
    s3_bucket = body.get("detail", {}).get("bucket", {}).get("name")
    s3_key = body.get("detail", {}).get("object", {}).get("key")
    if not s3_bucket or not s3_key:
        logger.error(f"S3 path or bucket not found in SQS message: {body}")
        sqs.delete_message(
            QueueUrl=os.getenv("SQS_QUEUE_URL"), ReceiptHandle=message["ReceiptHandle"]
        )
        continue

    file_id = os.path.splitext(os.path.basename(s3_key))[0]
    media_uri = f"s3://{s3_bucket}/{s3_key}"
    logger.info(f"Start transcription job for: {media_uri}")
    try:
        transcribe.start_transcription_job(
            TranscriptionJobName=file_id,
            Media={"MediaFileUri": media_uri},
            MediaFormat="mp4",
            LanguageCode="ja-JP",
            OutputBucketName=os.getenv("TRANSCRIBE_OUTPUT_BUCKET", "audio4output"),
        )
        logger.info(f"Transcription job started: {file_id}")

        # ジョブの完了を監視
        logger.info(f"Monitoring transcription job: {file_id}")
        while True:
            job_status = transcribe.get_transcription_job(TranscriptionJobName=file_id)
            status = job_status["TranscriptionJob"]["TranscriptionJobStatus"]

            if status == "COMPLETED":
                logger.info(f"Transcription job completed: {file_id}")
                # DynamoDBのtranscribedフラグを1に更新
                success = dynamodb_client.update_transcribed_status(file_id, True)
                if success:
                    logger.info(
                        f"DynamoDB transcribed flag updated to 1 for video: {file_id}"
                    )
                else:
                    logger.error(
                        f"Failed to update DynamoDB transcribed flag for video: {file_id}"
                    )
                break
            elif status == "FAILED":
                logger.error(f"Transcription job failed: {file_id}")
                # 失敗時はフラグを0のまま残す（更新しない）
                break
            else:
                logger.info(f"Transcription job status: {status}. Waiting...")
                import time

                time.sleep(30)  # 30秒待機

    except Exception as e:
        logger.error(f"Failed to start transcription job for {file_id}: {e}")

    # SQSメッセージを削除
    sqs.delete_message(
        QueueUrl=os.getenv("SQS_QUEUE_URL"), ReceiptHandle=message["ReceiptHandle"]
    )
