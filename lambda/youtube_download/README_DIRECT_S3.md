# YouTube Downloader with Direct S3 Upload

YouTube から音声をダウンロードし、S3 にアップロードする Ruby アプリケーション。

## 🚀 新機能: 直接 S3 ストリーミングアップロード

従来のローカルファイル保存を経由する方法に加え、**直接 S3 にストリーミングアップロード**する機能を追加しました。

### メリット

- ✅ **ディスク使用量ゼロ**: ローカルストレージを使用しません
- ✅ **メモリ効率**: 5MB チャンクでストリーミング処理
- ✅ **高速処理**: ダウンロードとアップロードが並行実行
- ✅ **AWS Lambda 対応**: 限られたディスク容量でも大きなファイルを処理可能

## 📋 設定

### 環境変数

```bash
# 必須設定
AWS_REGION=ap-northeast-1
S3_BUCKET_NAME=audio4gladia
DYNAMO_TABLE_NAME=YoutubeList

# 直接S3アップロードを有効化
DIRECT_S3_UPLOAD=true

# 従来のローカル保存方式（DIRECT_S3_UPLOAD=false の場合）
DOWNLOAD_OUTPUT_DIR=./downloads
UPLOAD_TO_S3=true
```

### 使用方法

#### 1. 直接 S3 アップロード（推奨）

```bash
# 環境変数を設定
export DIRECT_S3_UPLOAD=true

# 実行
ruby handler.rb
```

#### 2. ローカル保存後に S3 アップロード

```bash
# 環境変数を設定
export DIRECT_S3_UPLOAD=false
export UPLOAD_TO_S3=true

# 実行
ruby handler.rb
```

## 🧪 テスト

```bash
# テスト実行
ruby test_direct_s3.rb
```

## 🔧 技術仕様

### 直接 S3 アップロードの仕組み

1. **yt-dlp**で YouTube 音声を stdout にストリーミング
2. **S3 Multipart Upload**で 5MB チャンクずつ並行アップロード
3. **メモリバッファ**のみ使用（ディスク I/O なし）

### サポートフォーマット

- MP4 (優先)
- M4A
- WebM
- その他 yt-dlp が対応するオーディオフォーマット

### エラーハンドリング

- yt-dlp エラー時の自動フォールバック
- S3 Multipart Upload 失敗時の自動クリーンアップ
- DynamoDB 更新失敗時の詳細ログ

## 📊 パフォーマンス比較

| 方式     | ディスク使用量   | メモリ使用量 | 処理時間 |
| -------- | ---------------- | ------------ | -------- |
| 従来方式 | ファイルサイズ分 | 低           | 長い     |
| 直接 S3  | 0                | 5MB 程度     | 短い     |

## 🛠️ 依存関係

```ruby
gem 'aws-sdk-s3'
gem 'aws-sdk-dynamodb'
gem 'dotenv'
```

### システム要件

- Ruby 2.7+
- yt-dlp (pip install yt-dlp)
- AWS credentials 設定済み

## 🔍 ログ出力例

### 直接 S3 アップロード

```
🎬 Direct S3 download: https://www.youtube.com/watch?v=dQw4w9WgXcQ
📤 Streaming to S3: s3://audio4gladia/dQw4w9WgXcQ.mp4
📦 Uploaded part 1 (5242880 bytes)
📦 Uploaded part 2 (3145728 bytes)
✅ Successfully streamed to S3: dQw4w9WgXcQ.mp4
```

## 📝 注意事項

- Lambda 環境では`DIRECT_S3_UPLOAD=true`を推奨
- 大きなファイル（>100MB）では従来方式が安定する場合があります
- ネットワーク切断時は自動的にマルチパートアップロードがクリーンアップされます

## 🤝 貢献

プルリクエストやイシューは歓迎します！
