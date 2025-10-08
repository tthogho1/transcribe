#!/usr/bin/env ruby
# Direct S3 Upload Test Script

require_relative 'handler'
require 'ostruct'

puts "🧪 Testing YouTube Direct S3 Upload"
puts "=" * 50

# 環境変数の確認
required_env_vars = %w[S3_BUCKET_NAME AWS_REGION]
missing_vars = required_env_vars.select { |var| ENV[var].nil? || ENV[var].empty? }

if missing_vars.any?
  puts "❌ Missing environment variables: #{missing_vars.join(', ')}"
  puts "Please set these in your .env file"
  exit 1
end

puts "📋 Configuration:"
puts "  - S3 Bucket: #{ENV['S3_BUCKET_NAME']}"
puts "  - AWS Region: #{ENV['AWS_REGION']}"
puts "  - Direct S3 Upload: #{ENV['DIRECT_S3_UPLOAD']}"
puts "  - DynamoDB Table: #{ENV['DYNAMO_TABLE_NAME']}"
puts ""

begin
  downloader = YouTubeDownloader.new
  
  # テスト用のshort YouTube video ID
  # 実際のテストでは適切なvideo_idに変更してください
  test_video_id = "dQw4w9WgXcQ"  # Rick Roll (短い動画)
  
  puts "🎬 Testing with video ID: #{test_video_id}"
  puts "⏳ This may take a few minutes depending on the video length..."
  puts ""
  
  if ENV['DIRECT_S3_UPLOAD'] == 'true'
    puts "🚀 Using direct S3 streaming upload"
    result = downloader.send(:download_video_to_s3, test_video_id)
  else
    puts "📁 Using traditional local download then upload"
    result = downloader.send(:download_video, test_video_id)
  end
  
  puts ""
  puts "📊 Test Result:"
  puts "  - Success: #{result[:success]}"
  puts "  - Message: #{result[:message]}"
  
  if result[:success]
    puts "  - S3 Key: #{result[:s3_key]}" if result[:s3_key]
    puts "  - S3 URL: #{result[:s3_url]}" if result[:s3_url]
    puts "  - Parts Count: #{result[:parts_count]}" if result[:parts_count]
  end
  
  puts ""
  if result[:success]
    puts "🎉 Test completed successfully!"
    puts "The audio file has been uploaded to S3"
  else
    puts "❌ Test failed!"
    puts "Please check the error message above"
  end
  
rescue => e
  puts ""
  puts "💥 Test failed with exception:"
  puts "Error: #{e.message}"
  puts "Backtrace:"
  puts e.backtrace.first(5).join("\n")
end