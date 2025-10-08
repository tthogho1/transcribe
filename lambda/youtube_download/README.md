# YouTube Download Lambda

DynamoDBから転写フラグが`false`の動画IDを取得し、YouTubeから音声をMP4形式でダウンロードするRubyスクリプトです。

## 機能

- DynamoDBから未転写動画（`transcribed = 0`）を抽出
- yt-dlpを使用してYouTube動画を音声ファイルとしてダウンロード
- オプションでS3への自動アップロード
- Lambda関数として実行可能

## 前提条件

### 必要なツール
- Ruby 2.7+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)

### yt-dlpのインストール

```bash
# pip経由
pip install yt-dlp

# または Homebrew (macOS)
brew install yt-dlp

# または Windows Chocolatey
choco install yt-dlp
```

## セットアップ

1. **依存関係のインストール**
```bash
cd lambda/youtube_download
bundle install
```

2. **環境変数の設定**
```bash
# .envファイルをコピー
cp env.example .env

# .envファイルを編集して適切な値を設定
```

## 実行方法

### ローカル実行

```bash
ruby handler.rb
```

### PowerShell実行例

```powershell
# 環境変数を設定
$env:AWS_REGION="ap-northeast-1"
$env:DYNAMO_TABLE_NAME="YoutubeList"
$env:AWS_ACCESS_KEY_ID="your-access-key"
$env:AWS_SECRET_ACCESS_KEY="your-secret-key"
$env:DOWNLOAD_OUTPUT_DIR="./downloads"

# 実行
ruby handler.rb
```

## 環境変数

| 変数名 | 説明 | デフォルト値 |
|--------|------|-------------|
| `AWS_REGION` | AWSリージョン | `ap-northeast-1` |
| `AWS_ACCESS_KEY_ID` | AWS アクセスキーID | 必須 |
| `AWS_SECRET_ACCESS_KEY` | AWS シークレットアクセスキー | 必須 |
| `DYNAMO_TABLE_NAME` | DynamoDB テーブル名 | `YoutubeList` |
| `DOWNLOAD_OUTPUT_DIR` | ダウンロード先ディレクトリ | `./downloads` |
| `S3_BUCKET_NAME` | S3バケット名 | `audio4gladia` |
| `UPLOAD_TO_S3` | S3自動アップロード | `false` |

## 動作フロー

1. DynamoDBから`transcribed = 0`の動画レコードをスキャン
2. 各動画IDに対してyt-dlpでYouTubeダウンロードを実行
3. ダウンロードしたファイルを指定ディレクトリに保存
4. オプション: S3に自動アップロード
5. 処理結果をJSON形式で返却

## 出力例

```json
{
  "message": "YouTube download completed",
  "total_videos": 5,
  "successful_downloads": 4,
  "results": [
    {
      "video_id": "abc123",
      "success": true,
      "file_path": "./downloads/abc123.m4a",
      "message": "Download successful"
    },
    {
      "video_id": "def456",
      "success": false,
      "message": "Download failed: Video unavailable"
    }
  ]
}
```

## トラブルシューティング

### yt-dlpが見つからない
```bash
# パスを確認
which yt-dlp

# インストール確認
yt-dlp --version
```

### DynamoDB接続エラー
- AWS認証情報が正しく設定されているか確認
- DynamoDBテーブル名が正しいか確認
- IAM権限にDynamoDB:Scanが含まれているか確認

### ダウンロード失敗
- YouTube動画が利用可能か確認
- ネットワーク接続を確認
- yt-dlpのバージョンを最新に更新