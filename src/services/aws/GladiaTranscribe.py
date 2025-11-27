import binascii
import boto3
import logging
import os
import json
import requests
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from services.database.youtube_dynamodb_client import YouTubeDynamoDBClient

# ログ設定
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()


class GladiaTranscriber:
    """Gladia.ioを使用した音声転写クラス"""

    def __init__(self):
        """初期化"""
        self.gladia_api_key = os.getenv("GLADIA_API_KEY")
        self.gladia_base_url = os.getenv("GLADIA_API_URL", "https://api.gladia.io/v2/")

        if not self.gladia_api_key:
            raise ValueError("GLADIA_API_KEY環境変数が設定されていません")

        # AWS S3クライアント
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION"),
        )

        # SQSクライアント
        self.sqs_client = boto3.client(
            "sqs",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_REGION"),
        )

        self.output_bucket = os.getenv("TRANSCRIBE_OUTPUT_BUCKET", "audio4gladia")
        logger.info(
            f"✅ Gladia Transcriber initialized. Output bucket: {self.output_bucket}"
        )

        # DynamoDBクライアント初期化
        table_name = os.getenv("YOUTUBE_DYNAMODB_TABLE", "YoutubeList")
        self.dynamodb_client = YouTubeDynamoDBClient(table_name=table_name)
        logger.info("✅ DynamoDB client initialized")

    def upload_audio_to_gladia(self, s3_bucket: str, s3_key: str) -> str:
        """
        S3の音声ファイルをGladiaにアップロード

        Args:
            s3_bucket: S3バケット名
            s3_key: S3オブジェクトキー

        Returns:
            Gladiaの音声URL
        """
        try:
            # S3から音声ファイルを取得
            response = self.s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
            audio_data = response["Body"].read()
            content_type = response.get("ContentType", "audio/mp4")  # ← 追加

            if isinstance(audio_data, bytes) and len(audio_data) > 0:
                print("audio_data は有効なバイナリデータです。")
                print(binascii.hexlify(audio_data[:64]))  # 先頭64バイトを16進数で表示
            else:
                print("audio_data は空か、バイナリデータではありません。")

            # Gladiaにファイルをアップロード
            upload_url = f"{self.gladia_base_url}upload"
            headers = {
                "x-gladia-key": self.gladia_api_key,
            }

            files = {"audio": (os.path.basename(s3_key), audio_data, content_type)}

            logger.info(f"📤 Uploading audio file to Gladia: {s3_key}")
            upload_response = requests.post(upload_url, headers=headers, files=files)
            upload_response.raise_for_status()

            upload_result = upload_response.json()
            audio_url = upload_result.get("audio_url")

            if not audio_url:
                raise ValueError(
                    f"Gladiaからのレスポンスにaudio_urlがありません: {upload_result}"
                )

            logger.info(f"✅ Audio uploaded to Gladia: {audio_url}")
            return audio_url

        except Exception as e:
            logger.error(f"❌ Failed to upload audio to Gladia: {e}")
            raise

    def start_transcription(self, audio_url: str, file_id: str) -> str:
        """
        Gladiaで転写ジョブを開始

        Args:
            audio_url: Gladiaの音声URL
            file_id: ファイルID

        Returns:
            転写ジョブID
        """
        try:
            headers = {
                "x-gladia-key": self.gladia_api_key,
                "Content-Type": "application/json",
            }

            subtitles_config = {"formats": ["srt", "vtt"]}

            # 転写リクエストデータ
            transcription_data = {
                "audio_url": audio_url,
                "language": "ja",  # 日本語
                "subtitles": True,
                "detect_language": True,
                "subtitles_config": subtitles_config,
            }

            logger.info(f"🚀: {file_id}")
            url = f"{self.gladia_base_url}pre-recorded"
            response = requests.post(url, headers=headers, json=transcription_data)
            response.raise_for_status()

            result = response.json()
            job_id = result.get("id")
            result_url = result.get("result_url")

            if not job_id:
                raise ValueError(f"Gladiaからのレスポンスにidがありません: {result}")

            logger.info(f"✅ Transcription job started: {job_id}")
            return job_id, result_url

        except Exception as e:
            logger.error(f"❌ Failed to start Gladia transcription: {e}")
            raise

    def wait_for_completion(
        self, job_id: str, result_url, max_wait_time: int = 1800
    ) -> Dict[str, Any]:
        """
        転写ジョブの完了を待機

        Args:
            job_id: 転写ジョブID
            resulrt_url : 転写結果URL
            max_wait_time: 最大待機時間（秒）

        Returns:
            転写結果
        """
        headers = {
            "x-gladia-key": self.gladia_api_key,
        }

        start_time = time.time()

        while time.time() - start_time < max_wait_time:
            try:
                response = requests.get(f"{result_url}", headers=headers)
                response.raise_for_status()

                result = response.json()
                status = result.get("status")

                if status == "done":
                    logger.info(f"✅ Transcription completed: {job_id}")
                    return result
                elif status == "error":
                    error_msg = result.get("error", "Unknown error")
                    raise Exception(f"Gladia transcription failed: {error_msg}")
                else:
                    logger.info(f"⏳ Transcription in progress: {status}")
                    time.sleep(10)  # 10秒待機

            except Exception as e:
                logger.error(f"❌ Error checking transcription status: {e}")
                raise

        raise TimeoutError(f"Transcription timed out after {max_wait_time} seconds")

    def save_result_to_s3(self, result: Dict[str, Any], file_id: str) -> str:
        """
        転写結果をS3に保存

        Args:
            result: Gladiaの転写結果
            file_id: ファイルID

        Returns:
            S3オブジェクトキー
        """
        try:
            # 結果をJSON形式で変換
            transcription_json = {
                "status": "done",
                "results": {
                    "language": "",
                    "confidence": 0,
                    "transcription": {
                        "full_transcript": result.get("result", {})
                        .get("transcription", {})
                        .get("full_transcript", ""),
                        "utterances": [],
                    },
                },
            }

            # Gladiaの詳細結果がある場合は追加
            if "result" in result and "transcription" in result["result"]:
                gladia_result = result["result"]["transcription"]

                # 話者別の結果を処理
                if "utterances" in gladia_result:
                    for utterance in gladia_result["utterances"]:
                        item = {
                            "speaker": "",
                            "start": utterance.get("start", 0),
                            "end": utterance.get("end", 0),
                            "text": utterance.get("text", ""),
                        }
                        transcription_json["results"]["transcription"][
                            "utterances"
                        ].append(item)

            # S3にアップロード
            s3_key = f"{file_id}_transcription.json"

            self.s3_client.put_object(
                Bucket=self.output_bucket,
                Key=s3_key,
                Body=json.dumps(transcription_json, ensure_ascii=False, indent=2),
                ContentType="application/json",
                Metadata={
                    "transcription_engine": "gladia",
                    "original_job_id": result.get("id", ""),
                    "language": "ja",
                },
            )

            logger.info(
                f"✅ Transcription result saved to S3: s3://{self.output_bucket}/{s3_key}"
            )
            return s3_key

        except Exception as e:
            logger.error(f"❌ Failed to save transcription result to S3: {e}")
            raise

    def process_transcription(self, s3_bucket: str, s3_key: str, file_id: str) -> bool:
        """
        転写処理のメインフロー

        Args:
            s3_bucket: S3バケット名
            s3_key: S3オブジェクトキー
            file_id: ファイルID

        Returns:
            処理成功フラグ
        """
        try:
            logger.info(f"🎬 Starting transcription process for: {file_id}")

            # 1. 音声ファイルをGladiaにアップロード
            audio_url = self.upload_audio_to_gladia(s3_bucket, s3_key)

            # 2. 転写ジョブを開始
            job_id, result_url = self.start_transcription(audio_url, file_id)

            # 3. 転写完了を待機
            result = self.wait_for_completion(job_id, result_url)

            # 4. 結果をS3に保存
            self.save_result_to_s3(result, file_id)

            # 5. DynamoDBのtranscribedフラグを1に更新
            success = self.dynamodb_client.update_transcribed_status(file_id, True)
            if success:
                logger.info(
                    f"✅ DynamoDB transcribed flag updated to 1 for video: {file_id}"
                )
            else:
                logger.warning(
                    f"⚠️ Failed to update DynamoDB transcribed flag for video: {file_id}"
                )

            logger.info(
                f"🎉 Transcription process completed successfully for: {file_id}"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Transcription process failed for {file_id}: {e}")
            return False


def main():
    """メイン処理：SQSからメッセージを受信してGladia転写を実行"""
    try:
        transcriber = GladiaTranscriber()

        sqs_queue_url = os.getenv("SQS_QUEUE_URL")
        if not sqs_queue_url:
            raise ValueError("SQS_QUEUE_URL環境変数が設定されていません")

        logger.info(f"🚀 Gladia Transcription Worker started")
        logger.info(f"📋 SQS Queue URL: {sqs_queue_url}")

        # SQSからメッセージを受信してTranscribeを実行
        while True:
            try:
                response = transcriber.sqs_client.receive_message(
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
                    transcriber.sqs_client.delete_message(
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
