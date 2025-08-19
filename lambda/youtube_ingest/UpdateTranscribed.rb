require 'aws-sdk-dynamodb'
require 'dotenv/load'

# クライアントの初期化
dynamodb = Aws::DynamoDB::Client.new(
  region: 'ap-northeast-1',
  access_key_id: ENV['AWS_ACCESS_KEY_ID'],
  secret_access_key: ENV['AWS_SECRET_ACCESS_KEY']
)


# テーブル名を指定
table_name = 'YoutubeList'

# 全件スキャンで取得
resp = dynamodb.scan(table_name: table_name)

resp.items.each do |item|
  # Boolean型transcribedを数値へ変換
  transcribed_num = item['transcribed'] == true ? 1 : 0

  # 更新リクエスト
  dynamodb.update_item(
    table_name: table_name,
    key: { 'video_id' => item['video_id'] },
    update_expression: 'SET transcribed = :transcribed',
    expression_attribute_values: {
      ':transcribed' => transcribed_num
    }
  )

  puts "Updated video_id #{item['video_id']}: transcribed = #{transcribed_num}"
end