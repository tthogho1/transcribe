# Scripts Directory

このディレクトリには、DynamoDB データベースの管理とメンテナンス用スクリプトが含まれています。

## スクリプト一覧

### `generate_embeddings_with_vectorizer.py`

**目的**: DynamoDB で `embedding=false` の動画を対象に、S3 から転写 JSON を取得し、`ConversationVectorizer` を使ってエンベディングを生成・Zilliz に保存し、DynamoDB のフラグを更新します。

**機能**:

- DynamoDB から `embedding` が未設定/false の `video_id` を抽出
- S3 から `{video_id}_transcription.json` をダウンロード
- AWS Transcribe / Gladia 形式の JSON からテキストを抽出
- `ConversationVectorizer.process_monologue_bm25` でベクトル化し Zilliz Cloud (BM25 コレクション) に保存
- DynamoDB の `embedding` フラグと `embedding_updated_at` を更新
- ドライランモード・バッチサイズ指定・ログレベル指定に対応

**使用方法**:

```bash
# 1. 環境変数を確認
python scripts/generate_embeddings_with_vectorizer.py --dry-run --batch-size 3

# 2. 実際に 5 件処理
python scripts/generate_embeddings_with_vectorizer.py --batch-size 5

# 3. デバッグログを有効化
python scripts/generate_embeddings_with_vectorizer.py --log-level DEBUG
```

**必要な環境変数**:

- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `DYNAMO_TABLE_NAME`
- `S3_TRANSCRIPT_BUCKET` または `S3_BUCKET_NAME`
- `ZILLIZ_URI`, `ZILLIZ_TOKEN`

**注意**: 対象は `embedding` フラグだけで選ばれ、`transcribed` は見ていません。未転写の動画も対象になり、転写 JSON がないため失敗して `embedding = 0` のまま残り、バッチ枠を消費します。成功件数が 0 の場合は、先に転写を実行するか `--batch-size` を増やしてください。

### `gladia_transcribe/transcribe_untranscribed.py`

**目的**: DynamoDB で `transcribed = 0` の動画を Gladia で文字起こしします（通常はこちらを使用）。

- `audio4input` バケットから `{video_id}.m4a`、なければ `{video_id}.mp4` を探す
- 結果を `TRANSCRIBE_OUTPUT_BUCKET`（デフォルト `audio4gladia`）に `{video_id}_transcription.json` として保存し、`transcribed = 1` に更新
- 音声ファイルが S3 にない動画はスキップ（`transcribed = 0` のまま）
- オプションなし（最大 1000 件を処理。1 件ごとに Gladia の課金が発生）

```bash
python scripts/gladia_transcribe/transcribe_untranscribed.py
```

### `gladia_transcribe/transcribe_audio4input.py`

**目的**: S3 バケット内の `.mp4` をすべて Gladia で文字起こしします。DynamoDB は見ないため、転写済みのファイルも再度処理されます。`.m4a` は対象外です。

```bash
python scripts/gladia_transcribe/transcribe_audio4input.py --limit 1
python scripts/gladia_transcribe/transcribe_audio4input.py --prefix some/prefix/ --limit 5
```

### `embed_missing_embeddings.py`

`generate_embeddings_with_vectorizer.py` の旧版です。動画タイトルを保存しないため、通常は `generate_embeddings_with_vectorizer.py` を使用してください。

### `add_embedding_attribute.py`

**注意**: 既存データ移行用の一回限りのスクリプトです。再実行すると、転写済みでまだエンベディングされていない動画も `embedding = true` になり、エンベディングが生成されなくなります。

**目的**: DynamoDB テーブル内の全項目に新規属性`embedding`を追加

**機能**:

- DynamoDB テーブルの全アイテムをスキャン
- `transcribed = 1` の場合: `embedding = true`を設定
- それ以外の場合: `embedding = false`を設定
- バッチ処理による効率的な更新
- ドライランモード対応

**使用方法**:

```bash
# 1. ドライランでプレビュー
python scripts/add_embedding_attribute.py --dry-run

# 2. 実際の更新実行
python scripts/add_embedding_attribute.py

# 3. カスタムテーブル名での実行
python scripts/add_embedding_attribute.py --table-name MyTable

# 4. デバッグモード
python scripts/add_embedding_attribute.py --log-level DEBUG
```

## 環境設定

### 必要な環境変数

```bash
# AWS認証情報（必須）
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"

# オプション設定（デフォルト値あり）
export AWS_REGION="ap-northeast-1"
export DYNAMO_TABLE_NAME="YoutubeList"
```

### Python 依存関係

```bash
pip install boto3 python-dotenv
```

## 実行例

### 1. ドライラン実行

```bash
python scripts/add_embedding_attribute.py --dry-run
```

**出力例**:

```
🚀 Starting embedding attribute update for table: YoutubeList
🔍 Running in DRY RUN mode - no actual changes will be made
📋 Scanning all items...
📊 Total items scanned: 245

📊 Analysis Results:
   Total items: 245
   Transcribed (true/1): 15
   Transcribed (false/0): 230
   Transcribed (missing): 0
   Embedding attribute exists: 0
   Items needing update: 245

🔄 Updating 245 items...
[DRY RUN] Would update batch 1: 25 items
[DRY RUN] Would update batch 2: 25 items
...

🎯 [DRY RUN] Update Results:
   ✅ Success: 245
   ❌ Errors: 0
   ⏭️  Skipped: 0

🎉 [DRY RUN] All items updated successfully!
```

### 2. 実際の更新実行

```bash
python scripts/add_embedding_attribute.py
```

## トラブルシューティング

### よくある問題

1. **AWS 認証エラー**

   ```
   ❌ DynamoDB initialization failed: Unable to locate credentials
   ```

   **解決方法**: AWS 認証情報を正しく設定してください

2. **テーブルが見つからない**

   ```
   ❌ Table YoutubeList does not exist
   ```

   **解決方法**: テーブル名を確認するか、`--table-name`パラメータで指定してください

3. **権限不足**
   ```
   ❌ Access denied
   ```
   **解決方法**: IAM ユーザーに DynamoDB 読み取り・書き込み権限を付与してください

### 必要な IAM 権限

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:Scan", "dynamodb:UpdateItem", "dynamodb:DescribeTable"],
      "Resource": "arn:aws:dynamodb:*:*:table/YoutubeList"
    }
  ]
}
```

## ログレベル

- **DEBUG**: 最も詳細な情報
- **INFO**: 一般的な実行情報（デフォルト）
- **WARNING**: 警告メッセージのみ
- **ERROR**: エラーメッセージのみ

```bash
python scripts/add_embedding_attribute.py --log-level DEBUG
```
