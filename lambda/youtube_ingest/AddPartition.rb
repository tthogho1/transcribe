require 'aws-sdk-dynamodb'
require 'dotenv/load'

client = Aws::DynamoDB::Client.new(
  region: 'ap-northeast-1',
  access_key_id: ENV['AWS_ACCESS_KEY_ID'],
  secret_access_key: ENV['AWS_SECRET_ACCESS_KEY']
)

# テーブル名を指定
table_name = 'YoutubeList'
attribute_name = 'FORALL' # 更新する属性名
attribute_value = 'A'

# 全レコード取得
items = []
last_evaluated_key = nil

begin
  params = { table_name: table_name }
  params[:exclusive_start_key] = last_evaluated_key if last_evaluated_key

  result = client.scan(params)
  items.concat(result.items)
  last_evaluated_key = result.last_evaluated_key
end while last_evaluated_key

# 各レコードをアップデート
items.each do |item|
  key = {} # プライマリキー構築
  key['video_id'] = item['video_id'] # ※ここはテーブル定義に合わせて修正

  client.update_item(
    table_name: table_name,
    key: key,
    update_expression: "SET #{attribute_name} = :val",
    expression_attribute_values: {
      ":val" => attribute_value
    }
  )
end
