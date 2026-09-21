FROM ruby:3.2

# yt-dlp（単体バイナリ。Python同梱）をインストール
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) asset=yt-dlp_linux ;; \
      arm64) asset=yt-dlp_linux_aarch64 ;; \
      *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/yt-dlp/yt-dlp/releases/latest/download/${asset}" -o /usr/local/bin/yt-dlp; \
    chmod +x /usr/local/bin/yt-dlp; \
    yt-dlp --version

WORKDIR /app
COPY Gemfile Gemfile.lock ./
RUN bundle install

# アプリ本体をコピー
COPY . .

# コンテナのローカルディスクは実行後に消えるため、S3へ直接ストリーミングする
ENV DIRECT_S3_UPLOAD=true

# Lambda Entrypointではなく、バッチ用途なのでruby handler.rbをデフォルトコマンドに
CMD ["ruby", "handler.rb"]
