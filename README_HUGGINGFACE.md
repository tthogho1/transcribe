# 🤗 Hugging Face Spaces デプロイガイド（CPU 無料版）

この README は、Chat Server（BM25 + Ruri v3 によるハイブリッド RAG 検索）を
Hugging Face Spaces（Docker SDK, CPU Free Tier）にデプロイする手順を説明します。

## 📋 前提条件

- Hugging Face アカウント
- Zilliz Cloud アカウント（ベクトルデータベース、`conversation_chunks_bm25` コレクションにデータ投入済みであること）
- OpenAI API キー

## ⚠️ CPU 無料版の制約

Hugging Face Spaces の CPU 無料版では以下の制約があります：

- **CPU のみ**（GPU 不可）
- **メモリ**: 約 16GB
- **ストレージ**: 限定的
- **ビルド時間**: 制限あり
- **初回起動**: 依存パッケージのビルドと埋め込みモデル（`cl-nagoya/ruri-v3-310m`, 約 1.2GB）のダウンロードで 2-5 分

`Dockerfile.hfspaces` は CPU 専用の PyTorch ホイールを明示的にインストールすることで、
デフォルトの CUDA 同梱ビルドよりイメージサイズとビルド時間を削減しています。

## 🚀 デプロイ手順

### 1. Hugging Face Space の作成

1. [Hugging Face Spaces](https://huggingface.co/spaces)にアクセス
2. "Create new Space"をクリック
3. 以下の設定を選択:
   - **Space name**: 任意の名前（例: `conversation-chat-rag`）
   - **License**: MIT
   - **Space SDK**: **Docker**（重要！）
   - **Space hardware**: **CPU basic（無料）** ← これを選択

### 2. 必須ファイルの準備

以下のファイルを Space のリポジトリにアップロード:

```
transcribe/
├── Dockerfile              # Dockerfile.hfspaces をリネーム
├── requirements.txt
├── .dockerignore           # ビルドサイズ削減用
└── src/
    ├── api/
    │   └── chat_server.py
    ├── core/
    ├── services/
    ├── models/
    ├── templates/
    └── static/
```

**重要**: `Dockerfile.hfspaces` を `Dockerfile` にリネームしてアップロードしてください。
`requirements.txt` はプロジェクトのものをそのまま使用できます（CPU 最適化は Dockerfile 側で行うため、別ファイルは不要です）。

`.env` ファイルはアップロードしないでください（`.dockerignore` で除外済みです）。
シークレットは次の手順で Space 側の機能を使って設定します。

### 3. 環境変数の設定

Hugging Face Spaces の設定画面（Settings → Repository secrets）で以下を追加:

#### 必須の環境変数

| 変数名           | 説明                        | 例                                             |
| ---------------- | --------------------------- | ----------------------------------------------- |
| `ZILLIZ_URI`     | Zilliz Cloud エンドポイント | `https://xxx.serverless.xxx.cloud.zilliz.com`   |
| `ZILLIZ_TOKEN`   | Zilliz Cloud 認証トークン   | `xxxxxxxxxxxxxxxx`                              |
| `OPENAI_API_KEY` | OpenAI API キー             | `sk-xxxxxxxxxxxxxxxx`                           |

#### オプションの環境変数

| 変数名                | 説明                    | デフォルト値    |
| --------------------- | ----------------------- | --------------- |
| `OPENAI_MODEL`         | 使用する OpenAI モデル  | `gpt-3.5-turbo` |
| `OPENAI_MAX_TOKENS`    | 最大トークン数           | `2000`          |
| `OPENAI_TEMPERATURE`   | 温度パラメータ           | `0.7`           |
| `FLASK_PORT`           | ポート番号               | `7860`          |
| `FLASK_DEBUG`          | デバッグモード           | `False`         |

### 4. デプロイ

1. ファイルをアップロードまたは Git push でデプロイ
2. Hugging Face Spaces が自動的に Docker イメージをビルド
3. 初回ビルドには 5-10 分程度かかります（依存パッケージと埋め込みモデルのダウンロード）

### 5. 動作確認

デプロイ完了後、以下のエンドポイントにアクセス:

- **チャット UI**: `https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME`
- **ヘルスチェック**: `https://YOUR_USERNAME-YOUR_SPACE_NAME.hf.space/health`
- **API**: `https://YOUR_USERNAME-YOUR_SPACE_NAME.hf.space/api/chat`

## 📝 使用方法

### REST API

```bash
# チャット
curl -X POST https://YOUR_SPACE_URL/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "質問内容"}'

# 検索のみ（BM25ハイブリッド検索）
curl -X POST https://YOUR_SPACE_URL/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "検索クエリ", "limit": 5}'
```

### WebSocket (Socket.IO)

```javascript
const socket = io('https://YOUR_SPACE_URL');

socket.on('connect', () => {
  console.log('Connected');
});

socket.emit('chat_message', { query: '質問内容' });

socket.on('chat_response', data => {
  console.log('Answer:', data.answer);
  console.log('Sources:', data.sources);
});
```

## ⚙️ CPU 無料版向けパフォーマンス最適化

`Dockerfile.hfspaces` には CPU 負荷を抑えるための環境変数
（`OMP_NUM_THREADS=2`, `MKL_NUM_THREADS=2`, `TOKENIZERS_PARALLELISM=false`）が
すでに設定されています。追加で調整したい場合:

- **検索結果数を削減**: API 呼び出し時に `limit=3` を指定（デフォルトの 5 件から削減）
- **OpenAI モデルを変更**: `OPENAI_MODEL=gpt-3.5-turbo`（既定。GPT-4 系より高速）

## 🐛 トラブルシューティング

### ビルドが失敗する

**症状**: Docker イメージのビルドが途中で失敗
**原因**: ビルド時間制限超過またはメモリ不足
**対処**:

- `Dockerfile.hfspaces` を `Dockerfile` にリネームしてアップロードしているか確認
- `.dockerignore` が正しく設定されているか確認
- 不要なファイル（`typescript/`, `downloads/`, `scripts/`, `lambda/` 等）がアップロードされていないか確認

### 起動が遅い・タイムアウトする

**症状**: アプリケーションの起動に 5 分以上かかる
**原因**: 埋め込みモデル（`cl-nagoya/ruri-v3-310m`, 約 1.2GB）の初回ダウンロード
**対処**:

- **正常な動作です**。初回は 2-5 分かかります
- Space に永続ストレージを設定していない場合、Space の再ビルドのたびに再ダウンロードが発生します
- Hugging Face Spaces のログで進捗を確認できます

### 接続エラー / Zilliz エラー

**症状**: `Connection failed` または `Authentication failed`
**原因**: 環境変数の設定ミス
**対処**:

1. Hugging Face Spaces の「Settings」→「Repository secrets」を確認
2. 必須変数が設定されているか確認:
   - `ZILLIZ_URI`
   - `ZILLIZ_TOKEN`
   - `OPENAI_API_KEY`
3. `/health` エンドポイントで各サービスの状態を確認（`zilliz: "connected"` になっているか）

### Space がスリープ状態になる

**症状**: しばらくアクセスしないと応答しなくなる
**原因**: CPU 無料版は一定時間非アクティブでスリープ
**対処**:

- **正常な動作です**。再アクセス時に自動的に起動します（~30 秒）
- 有料プラン（CPU upgrade）でスリープを回避可能

## 📦 含まれるコンポーネント

- **Flask + Socket.IO**: Web サーバー・リアルタイム双方向通信
- **Sentence Transformers（cl-nagoya/ruri-v3-310m）**: 日本語埋め込みモデル（クエリ/文書非対称プレフィックス対応）
- **Zilliz Cloud（ネイティブ BM25 Function）**: 密ベクトル + BM25 疎ベクトルのハイブリッド検索。
  日本語トークナイズ（lindera/ipadic）は Zilliz Cloud 側で実行されるため、クライアント側に
  MeCab 等の日本語形態素解析ライブラリは不要です
- **OpenAI GPT**: 回答生成

## 🔒 セキュリティ

- API キーは必ず Hugging Face Spaces のシークレット機能を使用
- `.env` ファイルはリポジトリにコミット・アップロードしない（`.dockerignore` で除外済み）
- 本番環境では `FLASK_DEBUG=False` を設定

## 📄 ライセンス

このプロジェクトのライセンスに従います。

## 🆘 サポート

問題が発生した場合は、Issues セクションで報告してください。
