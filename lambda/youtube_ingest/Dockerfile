FROM ruby:3.2
WORKDIR /app
COPY Gemfile Gemfile.lock ./
RUN bundle install

# アプリ本体をコピー
COPY . .

# Lambda Entrypointではなく、バッチ用途なのでruby handler.rbをデフォルトコマンドに
CMD ["ruby", "handler.rb"]
