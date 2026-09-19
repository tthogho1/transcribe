require 'json'
require 'aws-sdk-dynamodb'
require 'aws-sdk-s3'  # S3 SDKを明示的に追加
require 'open3'
require 'fileutils'
require 'ostruct'

# .envファイルを読み込む（ローカル実行時）
begin
  require 'dotenv'
  Dotenv.load('.env')
  puts "✅ .env file loaded successfully"
rescue LoadError
  # dotenv gemが利用できない場合はスキップ
  puts "⚠️ dotenv gem not available, using system environment variables"
end

class YouTubeDownloader
  def initialize
    begin
      puts "🔧 Initializing YouTubeDownloader..."
      
      # 環境変数の確認
      puts "📋 Configuration:"
      puts "  - AWS Region: #{ENV['AWS_REGION'] || 'ap-northeast-1'}"
      puts "  - DynamoDB Table: #{ENV['DYNAMO_TABLE_NAME'] || 'YoutubeList'}"
      puts "  - S3 Bucket: #{ENV['S3_BUCKET_NAME'] || 'audio4input'}"
      puts "  - Direct S3 Upload: #{ENV['DIRECT_S3_UPLOAD']}"
      
      # DynamoDBクライアント初期化
      puts "🗃️ Initializing DynamoDB client..."
      @dynamodb = Aws::DynamoDB::Client.new(region: ENV['AWS_REGION'] || 'ap-northeast-1')
      puts "✅ DynamoDB client initialized"
      
      @table_name = ENV['DYNAMO_TABLE_NAME'] || 'YoutubeList'
      @output_dir = ENV['DOWNLOAD_OUTPUT_DIR'] || './downloads'
      @s3_bucket = ENV['S3_BUCKET_NAME'] || 'audio4input'
      
      # S3クライアント初期化
      puts "🪣 Initializing S3 client..."
      @s3_client = Aws::S3::Client.new(region: ENV['AWS_REGION'] || 'ap-northeast-1')
      puts "✅ S3 client initialized"
      
      # 出力ディレクトリを作成（ローカル保存時のみ必要）
      unless ENV['DIRECT_S3_UPLOAD'] == 'true'
        puts "📁 Creating output directory: #{@output_dir}"
        FileUtils.mkdir_p(@output_dir)
      end
      
      puts "🎉 YouTubeDownloader initialized successfully!"
      
    rescue => e
      puts "❌ Error during YouTubeDownloader initialization:"
      puts "  Error: #{e.message}"
      puts "  Class: #{e.class}"
      puts "  Backtrace:"
      puts e.backtrace.first(5).join("\n")
      raise e
    end
  end

  def lambda_handler(event:, context:)
    begin
      puts "🚀 YouTube Download Lambda started"
      
      # DynamoDBから転写フラグがfalseの動画を取得
      untranscribed_videos = fetch_untranscribed_videos
      
      if untranscribed_videos.empty?
        puts "✅ No untranscribed videos found"
        return {
          statusCode: 200,
          body: JSON.generate({
            message: "No untranscribed videos to download",
            processed_count: 0
          })
        }
      end

      puts "📋 Found #{untranscribed_videos.length} untranscribed videos"
      
      # 各動画をダウンロード
      download_results = []
      untranscribed_videos.each_with_index do |video, index|
        puts "📥 Processing video #{index + 1}/#{untranscribed_videos.length}: #{video['video_id']}"
        
        # 直接S3アップロードか通常ダウンロードかを選択
        if ENV['DIRECT_S3_UPLOAD'] == 'true'
          result = download_video_to_s3(video['video_id'])
        else
          result = download_video(video['video_id'])
        end
        
        download_results << result
        
        # Lambda実行時間制限を考慮して適度に休憩
        sleep(1) if index < untranscribed_videos.length - 1
      end

      successful_downloads = download_results.count { |r| r[:success] }
      
      puts "✅ Download completed: #{successful_downloads}/#{download_results.length} successful"

      {
        statusCode: 200,
        body: JSON.generate({
          message: "YouTube download completed",
          total_videos: untranscribed_videos.length,
          successful_downloads: successful_downloads,
          results: download_results
        })
      }

    rescue => e
      puts "❌ Error in lambda_handler: #{e.message}"
      puts e.backtrace

      {
        statusCode: 500,
        body: JSON.generate({
          error: "Internal server error",
          message: e.message
        })
      }
    end
  end

  private

  def find_yt_dlp_executable
    # 可能性のあるyt-dlpのパス
    possible_paths = [
      'yt-dlp',                                    # システムPATH
      'yt-dlp.exe',                               # Windows実行ファイル
      File.join(ENV['HOME'] || ENV['USERPROFILE'], '.local', 'bin', 'yt-dlp'),  # ユーザーローカル
      'c:/temp/SourceCode/transcribe/.venv/Scripts/yt-dlp.exe',  # venv環境
      'c:/temp/SourceCode/transcribe/.venv/Scripts/yt-dlp',      # venv環境（拡張子なし）
    ]
    
    # 環境変数からPythonパスを推測
    if ENV['VIRTUAL_ENV']
      venv_path = File.join(ENV['VIRTUAL_ENV'], 'Scripts', 'yt-dlp.exe')
      possible_paths << venv_path
    end
    
    possible_paths.each do |path|
      next if path.nil? || path.empty?
      
      begin
        # --version で実行可能かテスト
        _stdout, _stderr, status = Open3.capture3(path, '--version')
        if status.success?
          puts "✅ Found yt-dlp at: #{path}"
          return path
        end
      rescue
        # 次のパスを試す
        next
      end
    end
    
    puts "❌ yt-dlp not found in any of the expected locations:"
    possible_paths.each { |path| puts "   - #{path}" }
    puts ""
    puts "Please install yt-dlp:"
    puts "   pip install yt-dlp  # システム全体"
    puts "   または"
    puts "   .venv\\Scripts\\Activate.ps1 && pip install yt-dlp  # venv環境"
    
    nil
  end

  def fetch_untranscribed_videos
    videos = []
    scan_params = {
      table_name: @table_name,
      filter_expression: '#transcribed = :false_val',
      expression_attribute_names: {
        '#transcribed' => 'transcribed'
      },
      expression_attribute_values: {
        ':false_val' => 0  # DynamoDBでは数値0でfalseを表現
      },
      projection_expression: 'video_id, title'
    }

    begin
      loop do
        result = @dynamodb.scan(scan_params)
        videos.concat(result.items)
        
        break unless result.last_evaluated_key
        scan_params[:exclusive_start_key] = result.last_evaluated_key
      end
      
      puts "🔍 Found #{videos.length} untranscribed videos in DynamoDB"
      videos
      
    rescue Aws::DynamoDB::Errors::ServiceError => e
      puts "❌ DynamoDB error: #{e.message}"
      []
    end
  end

  def download_video(video_id)
    youtube_url = "https://www.youtube.com/watch?v=#{video_id}"
    output_path = File.join(@output_dir, "#{video_id}.%(ext)s")
    
    # yt-dlpのパスを検索
    yt_dlp_path = find_yt_dlp_executable
    unless yt_dlp_path
      return {
        video_id: video_id,
        success: false,
        message: "yt-dlp not found. Please install with: pip install yt-dlp"
      }
    end
    
    # yt-dlpコマンドを構築（音声用）
    # android_vrクライアントはSABR-onlyでURLが欠落することがあるため、webクライアントを明示指定
    cmd = [
      yt_dlp_path,  # フルパスを使用
      '--no-update',
      '--format', 'bestaudio/best',  # 利用可能な最良の音声（フォーマット限定を緩和）
      '--extractor-args', 'youtube:player_client=web',
      '--extractor-args', 'youtube:skip=hls,dash',
      '--output', output_path,
      '--no-playlist',
      youtube_url
    ]

    puts "🎬 Downloading: #{youtube_url}"
    puts "📁 Output path: #{output_path}"
    puts "🔧 Using yt-dlp: #{yt_dlp_path}"
    
    begin
      # yt-dlpコマンド実行
      _stdout, stderr, status = Open3.capture3(*cmd)

      # ダウンロードされたファイルの存在を優先して成功判定
      downloaded_file = find_downloaded_file(video_id)
      if status.success? || downloaded_file
        if downloaded_file
          puts "✅ Successfully downloaded: #{downloaded_file}"

          # S3にアップロード（オプション）
          if ENV['UPLOAD_TO_S3'] == 'true'
            upload_to_s3(downloaded_file, video_id)
          end

          {
            video_id: video_id,
            success: true,
            file_path: downloaded_file,
            message: "Download successful"
          }
        else
          # yt-dlpは成功を返したがファイルが見つからない（想定外）
          puts "⚠️ yt-dlp reported success but file not found for: #{video_id}"
          {
            video_id: video_id,
            success: false,
            message: "yt-dlp succeeded but output file not found"
          }
        end
      else
        puts "❌ Download failed for #{video_id}: #{stderr}"
        {
          video_id: video_id,
          success: false,
          message: "Download failed: #{stderr.strip}"
        }
      end
      
    rescue => e
      puts "❌ Exception during download for #{video_id}: #{e.message}"
      {
        video_id: video_id,
        success: false,
        message: "Exception: #{e.message}"
      }
    end
  end

  def download_video_to_s3(video_id)
    # YouTube動画を直接S3にストリーミングアップロード
    # ローカルディスクを使わずにメモリ効率的な処理を実現
    youtube_url = "https://www.youtube.com/watch?v=#{video_id}"
    
    # yt-dlpのパスを検索
    yt_dlp_path = find_yt_dlp_executable
    unless yt_dlp_path
      return {
        video_id: video_id,
        success: false,
        message: "yt-dlp not found. Please install with: pip install yt-dlp"
      }
    end
    
    puts "🎬 Direct S3 download: #{youtube_url}"
    puts "🔧 Using yt-dlp: #{yt_dlp_path}"
    
    begin
      # まずファイル情報を取得してファイル名を決定
      info_cmd = [
        yt_dlp_path,
        '--no-update',
        '--print', 'filename',
        '--format', 'bestaudio[ext=m4a]/bestaudio',
        '--no-playlist',
        '--extractor-args', 'youtube:player_client=web',
        '--extractor-args', 'youtube:skip=hls,dash',
        '--output', "#{video_id}.%(ext)s",
        youtube_url
      ]
      
      _stdout, _stderr, status = Open3.capture3(*info_cmd)
      unless status.success?
        return {
          video_id: video_id,
          success: false,
          message: "Failed to get file info"
        }
      end
      
      filename = _stdout.strip
      file_extension = File.extname(filename)
      s3_key = "#{video_id}#{file_extension}"
      
      # yt-dlpから標準出力にストリーミング
      stream_cmd = [
        yt_dlp_path,
        '--no-update',
        '--format', 'bestaudio[ext=m4a]/bestaudio',
        '--no-playlist',
        '--extractor-args', 'youtube:player_client=web',  # webクライアントのみ使用
        '--extractor-args', 'youtube:skip=hls,dash',  # HLS/DASHをスキップ
        '--output', '-',  # 標準出力に出力
        youtube_url
      ]
      
      puts "📤 Streaming to S3: s3://#{@s3_bucket}/#{s3_key}"
      
      # パイプを使用してyt-dlpの出力を直接S3にストリーミング
      Open3.popen3(*stream_cmd) do |stdin, stdout, stderr, wait_thr|
        stdin.close
        
        # stderrを別スレッドで読み取り（ブロック防止）
        error_output = []
        stderr_thread = Thread.new do
          stderr.each_line do |line|
            error_output << line
            puts "yt-dlp: #{line.strip}"
          end
        end
        
        # S3へのマルチパートアップロードを開始
        multipart_upload = @s3_client.create_multipart_upload(
          bucket: @s3_bucket,
          key: s3_key,
          content_type: get_content_type(file_extension)
        )
        
        upload_id = multipart_upload.upload_id
        puts "🟢 Multipart upload started: upload_id=#{upload_id}"
        
        parts = []
        part_number = 1
        chunk_size = 5 * 1024 * 1024  # 5MB chunks
        
        begin
          puts "🟢 Starting to read chunks from yt-dlp..."
          puts "🔎 stdout ready? #{!stdout.closed?}"
          
          while chunk = stdout.read(chunk_size)
            puts "🔎 Read attempt - chunk nil? #{chunk.nil?}, empty? #{chunk&.empty?}"
            break if chunk.nil? || chunk.empty?
            
            puts "🟢 Read chunk: #{chunk.length} bytes"
            
            # チャンクをS3にアップロード
            part_response = @s3_client.upload_part(
              bucket: @s3_bucket,
              key: s3_key,
              part_number: part_number,
              upload_id: upload_id,
              body: chunk
            )
            
            etag_value = part_response.etag
            puts "🔎 Raw ETag: #{etag_value.inspect}"
            puts "🔎 ETag class: #{etag_value.class}"
            
            # ETagがクォートで囲まれているか確認し、なければ追加
            etag_value = "\"#{etag_value}\"" unless etag_value.start_with?('"')

            parts << {
              etag: etag_value,
              part_number: part_number
            }
            
            part_number += 1
            puts "📦 Uploaded part #{part_number - 1} (#{chunk.length} bytes)"
          end
          
          puts "🟢 Finished reading chunks. Total parts: #{parts.length}"
          
          # stderrスレッドの終了を待つ
          stderr_thread.join
          
          # yt-dlpの終了ステータスを確認
          exit_status = wait_thr.value
          puts "🔎 yt-dlp exit status: #{exit_status.exitstatus}"
          
          if !error_output.empty?
            puts "⚠️ yt-dlp errors/warnings:"
            error_output.each { |line| puts "  #{line.strip}" }
          end
          
          # parts配列が空でないか確認
          if parts.empty?
            puts "❌ No parts uploaded, aborting multipart upload"
            @s3_client.abort_multipart_upload(
              bucket: @s3_bucket,
              key: s3_key,
              upload_id: upload_id
            )
            
            return {
              video_id: video_id,
              success: false,
              message: "No data received from yt-dlp"
            }
          end
          
          puts "🔧 Completing multipart upload with #{parts.length} parts"
          puts "🔎 Parts array: #{parts.inspect}"
          
          # マルチパートアップロードを完了
          @s3_client.complete_multipart_upload(
            bucket: @s3_bucket,
            key: s3_key,
            upload_id: upload_id,
            multipart_upload: {
              parts: parts
            }
          )
          
          exit_status = wait_thr.value
          
          if exit_status.success? && !parts.empty?
            puts "✅ Successfully streamed to S3: #{s3_key}"
            {
              video_id: video_id,
              success: true,
              s3_key: s3_key,
              s3_url: "s3://#{@s3_bucket}/#{s3_key}",
              parts_count: parts.length,
              message: "Direct S3 upload successful"
            }
          else
            # アップロードを中止
            @s3_client.abort_multipart_upload(
              bucket: @s3_bucket,
              key: s3_key,
              upload_id: upload_id
            )
            
            error_output = stderr.read || "Unknown error"
            puts "❌ Stream upload failed for #{video_id}: #{error_output}"
            {
              video_id: video_id,
              success: false,
              message: "Stream upload failed: #{error_output.strip}"
            }
          end
          
        rescue => upload_error
          # エラー時はマルチパートアップロードを中止
          begin
            @s3_client.abort_multipart_upload(
              bucket: @s3_bucket,
              key: s3_key,
              upload_id: upload_id
            )
          rescue
            # 中止にも失敗した場合は警告のみ
            puts "⚠️ Failed to abort multipart upload for #{s3_key}"
          end
          
          raise upload_error
        end
      end
      
    rescue => e
      puts "❌ Exception during direct S3 upload for #{video_id}: #{e.message}"
      {
        video_id: video_id,
        success: false,
        message: "Exception: #{e.message}"
      }
    end
  end

  def get_content_type(file_extension)
    case file_extension.downcase
    when '.mp4', '.m4a'
      'audio/mp4'
    when '.mp3'
      'audio/mpeg'
    when '.webm'
      'audio/webm'
    when '.ogg'
      'audio/ogg'
    else
      'audio/mpeg'  # デフォルト
    end
  end

  def find_downloaded_file(video_id)
    # 一般的な拡張子でファイルを検索
    extensions = %w[mp4 m4a webm mkv]
    
    extensions.each do |ext|
      file_path = File.join(@output_dir, "#{video_id}.#{ext}")
      return file_path if File.exist?(file_path)
    end
    
    # パターンマッチでファイルを検索
    pattern = File.join(@output_dir, "#{video_id}.*")
    matches = Dir.glob(pattern)
    matches.first if matches.any?
  end

  def upload_to_s3(file_path, video_id)
    begin
      require 'aws-sdk-s3'
      
      s3_client = Aws::S3::Client.new(region: ENV['AWS_REGION'] || 'ap-northeast-1')
      
      File.open(file_path, 'rb') do |file|
        # Flat key (no video_id "folder" prefix) so downstream Gladia
        # transcription scripts, which look up "#{video_id}#{ext}" at the
        # bucket root, can find the uploaded file.
        key = "#{video_id}#{File.extname(file_path)}"

        s3_client.put_object(
          bucket: @s3_bucket,
          key: key,
          body: file,
          content_type: get_content_type(File.extname(file_path))
        )

        puts "📤 Uploaded to S3: s3://#{@s3_bucket}/#{key}"
      end
      
    rescue => e
      puts "❌ S3 upload failed: #{e.message}"
    end
  end
end

# Lambda関数のエントリーポイント
def lambda_handler(event:, context:)
  downloader = YouTubeDownloader.new
  downloader.lambda_handler(event: event, context: context)
end

# ローカル実行用
if __FILE__ == $0
  # 疑似eventとcontextでテスト実行
  fake_event = {}
  fake_context = OpenStruct.new(
    function_name: 'youtube-downloader',
    aws_request_id: 'test-request-id'
  )
  
  result = lambda_handler(event: fake_event, context: fake_context)
  puts "\n🎯 Final Result:"
  puts JSON.pretty_generate(JSON.parse(result[:body]))
end