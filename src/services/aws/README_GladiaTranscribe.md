# Gladia Transcription Service Configuration

## 環境変数設定

以下の環境変数を`.env`ファイルまたはシステム環境変数として設定してください：

```env
# Gladia.io API設定
GLADIA_API_KEY=your_gladia_api_key_here

# AWS設定（AmazonTranscribe.pyと共通）
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=ap-northeast-1

# SQS設定（AmazonTranscribe.pyと共通）
SQS_QUEUE_URL=https://sqs.ap-northeast-1.amazonaws.com/xxx/transcribe-queue

# S3出力設定
TRANSCRIBE_OUTPUT_BUCKET=audio4gladia
```

## Gladia.io API Key 取得方法

1. [Gladia.io](https://gladia.io) にアカウント登録
2. ダッシュボードから API Key を取得
3. 上記の`GLADIA_API_KEY`に設定

## 実行方法

```bash
# 必要なPythonパッケージをインストール
pip install boto3 requests python-dotenv

# スクリプト実行
python src/services/aws/GladiaTranscribe.py
```

## 処理フロー

1. **SQS メッセージ受信**: AWS TranscribeWorker と同じ SQS キューを監視
2. **S3 音声ファイル取得**: メッセージから音声ファイル情報を抽出
3. **Gladia アップロード**: 音声ファイルを Gladia.io にアップロード
4. **転写ジョブ開始**: Gladia.io で日本語音声転写を開始
5. **完了待機**: ジョブ完了まで定期的にステータス確認
6. **結果保存**: 転写結果を S3 に保存（AWS Transcribe と同じ形式）
7. **メッセージ削除**: SQS メッセージを削除

## 出力形式

AWS Transcribe と互換性のある JSON 形式で出力：

```json
{
  "jobName": "video_id",
  "accountId": "gladia",
  "results": {
    "transcripts": [
      {
        "transcript": "転写されたテキスト全文"
      }
    ],
    "items": [
      {
        "start_time": "0.0",
        "end_time": "2.5",
        "alternatives": [
          {
            "confidence": "0.95",
            "content": "こんにちは"
          }
        ],
        "type": "pronunciation",
        "speaker_label": "spk_0"
      }
    ]
  }
}
```

## Gladia.io の利点

- **高精度**: 特に日本語音声の認識精度が高い
- **話者識別**: 複数話者の自動識別
- **リアルタイム処理**: AWS Transcribe より高速
- **コスト効率**: 従量課金制で小規模利用に最適

## 障害対応

### よくある問題

1. **API Key エラー**:

   ```
   ❌ Failed to upload audio to Gladia: 401 Unauthorized
   ```

   → `GLADIA_API_KEY`を確認してください

2. **音声ファイル形式エラー**:

   ```
   ❌ Failed to start Gladia transcription: Unsupported file format
   ```

   → MP4/M4A/WAV 形式をサポート

3. **タイムアウト**:
   ```
   ❌ Transcription timed out after 1800 seconds
   ```
   → 長い音声ファイルの場合は`max_wait_time`を調整

## 並列実行

AWS TranscribeWorker と同時実行可能：

```bash
# ターミナル1: AWS Transcribe Worker
python src/services/aws/AmazonTranscribe.py

# ターミナル2: Gladia Transcribe Worker
python src/services/aws/GladiaTranscribe.py
```

両方のワーカーが同じ SQS キューを監視し、先に処理できた方が転写を実行します。
