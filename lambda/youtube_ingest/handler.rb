
# #!/usr/bin/env ruby
require 'dotenv/load'
require 'json'
require 'uri'
require 'net/http'
require 'time'
require 'aws-sdk-dynamodb'

# Environment
TABLE_NAME = ENV.fetch('DYNAMO_TABLE_NAME') { raise 'DYNAMO_TABLE_NAME is required' }
YT_API_KEY = ENV.fetch('YOUTUBE_API_KEY') { raise 'YOUTUBE_API_KEY is required' }
CHANNEL_ID = ENV['CHANNEL_ID']
 

# Get the channel's uploads playlist id via channels endpoint
def youtube_channel_uploads_playlist_id(api_key, channel_id)
  uri = URI("https://www.googleapis.com/youtube/v3/channels?part=contentDetails&id=#{channel_id}&key=#{api_key}")
  res = Net::HTTP.get_response(uri)
  raise "YouTube API error: #{res.code} #{res.body}" unless res.is_a?(Net::HTTPSuccess)
  body = JSON.parse(res.body)
  item = body.fetch('items', []).first
  raise 'Channel not found' unless item
  uploads = item.dig('contentDetails', 'relatedPlaylists', 'uploads')
  raise 'Uploads playlist not available' unless uploads
  uploads
end

def enrich_items_with_view_counts_and_duration(api_key, items)
  ids = items.map { |it| it['video_id'] }.compact
  combined = {}
  ids.each_slice(50) do |slice|
    combined.merge!(youtube_get_view_counts_map(api_key, slice))
  end
  items.each do |it|
    stats = combined[it['video_id']] || {}
    it['views'] = stats['views'] || 0
    iso = stats['duration'] || ''
    secs = parse_iso8601_duration_to_seconds(iso)
    it['duration'] = format_seconds_to_hms(secs)
  end
  items
end

# --- Duration helpers ---
def parse_iso8601_duration_to_seconds(iso)
  return 0 if iso.nil? || iso.empty?
  # Supports PnDTnHnMnS (days optional)
  m = /P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/.match(iso)
  return 0 unless m
  days = (m[1] || '0').to_i
  h = (m[2] || '0').to_i
  min = (m[3] || '0').to_i
  s = (m[4] || '0').to_i
  days * 86400 + h * 3600 + min * 60 + s
end

def format_seconds_to_hms(total)
  total = total.to_i
  h = total / 3600
  m = (total % 3600) / 60
  s = total % 60
  sprintf('%02d:%02d:%02d', h, m, s)
end

# List uploads from a channel via playlistItems
def youtube_list_channel_uploads(api_key, channel_id, page_token: nil, max_results: 50)
  max = [[max_results.to_i, 1].max, 50].min
  playlist_id = youtube_channel_uploads_playlist_id(api_key, channel_id)
  qs = {
    part: 'snippet,contentDetails',
    playlistId: playlist_id,
    maxResults: max,
    key: api_key
  }
  qs[:pageToken] = page_token if page_token && !page_token.empty?
  uri = URI('https://www.googleapis.com/youtube/v3/playlistItems')
  uri.query = URI.encode_www_form(qs)

  puts uri.to_s 
  res = Net::HTTP.get_response(uri)
  raise "YouTube API error: #{res.code} #{res.body}" unless res.is_a?(Net::HTTPSuccess)
  body = JSON.parse(res.body)

  #puts body

  items = (body['items'] || []).map do |it|
    snip = it['snippet'] || {}
    cdet = it['contentDetails'] || {}
    {
      'video_id' => cdet['videoId'],
      'title' => snip['title'],
      'author' => snip['channelTitle'],
      'published_at' => snip['publishedAt'],
      'description' => snip['description'],
      'url' => "https://www.youtube.com/watch?v=#{cdet['videoId']}"
    }
  end

  {
    items: items,
    next_page_token: body['nextPageToken']
  }
end

# Fetch all uploads by following nextPageToken until exhausted
def youtube_list_all_channel_uploads(api_key, channel_id, per_page: 50)
  next_token = nil
  all_items = []
  loop do
    page = youtube_list_channel_uploads(api_key, channel_id, page_token: next_token, max_results: per_page)

    all_items.concat(page[:items])
    next_token = page[:next_page_token]
    break if next_token.nil? || next_token.empty?
  end
  { items: all_items }
end

# Fetch view counts for up to 50 video IDs at a time and return a map { id => Integer }
def youtube_get_view_counts_map(api_key, video_ids)
  # Returns { video_id => { 'views' => Integer, 'duration' => String } }
  return {} if video_ids.nil? || video_ids.empty?
  ids = video_ids.join(',')
  uri = URI("https://www.googleapis.com/youtube/v3/videos?part=statistics,contentDetails&id=#{ids}&key=#{api_key}")
  res = Net::HTTP.get_response(uri)
  raise "YouTube API error: #{res.code} #{res.body}" unless res.is_a?(Net::HTTPSuccess)
  body = JSON.parse(res.body)
  map = {}
  (body['items'] || []).each do |it|
    stats = it['statistics'] || {}
    details = it['contentDetails'] || {}
    map[it['id']] = {
      'views' => (stats['viewCount'] || '0').to_i,
      'duration' => details['duration'] || ''
    }
  end
  map
end

def put_item(dynamodb, table, item)
  dynamodb.put_item(
    table_name: table,
    item: item.transform_values { |v| v.nil? ? '' : v }
  )
end

# Lambda handler
def handler(event:, context: nil)
  # Inputs come only from environment variables (dotenv supported)

  channel_id = CHANNEL_ID
  per_page = (ENV['MAX_RESULTS'] || 50).to_i
  list = youtube_list_all_channel_uploads(YT_API_KEY, channel_id, per_page: per_page)
  items_enriched = enrich_items_with_view_counts_and_duration(YT_API_KEY, list[:items])
  dynamodb = Aws::DynamoDB::Client.new
  registered = []
  items_enriched.each do |v|
    item = {
      'video_id'    => v['video_id'],
      'title'       => v['title'],
      'author'      => v['author'],
      'duration'    => v['duration'],
      'views'       => v['views'],
      'description' => v['description'],
      'url'         => v['url'],
      'transcribed' => false,
      'created_at'  => v['published_at'] || v['created_at'],
      'updated_at'  => Time.now.utc.iso8601
    }

    puts item

    # Check if item exists by video_id
    resp = dynamodb.get_item(
      table_name: TABLE_NAME,
      key: { 'video_id' => v['video_id'] }
    )
    if resp.item
      # Update only views, created_at, updated_at
      dynamodb.update_item(
        table_name: TABLE_NAME,
        key: { 'video_id' => v['video_id'] },
        update_expression: 'SET #v = :views, #ca = :created_at, #ua = :updated_at',
        expression_attribute_names: {
          '#v' => 'views',
          '#ca' => 'created_at',
          '#ua' => 'updated_at'
        },
        expression_attribute_values: {
          ':views' => v['views'],
          ':created_at' => item['created_at'],
          ':updated_at' => item['updated_at']
        }
      )
      registered << resp.item.merge('views' => v['views'], 'created_at' => item['created_at'], 'updated_at' => item['updated_at'])
    else
      put_item(dynamodb, TABLE_NAME, item)
      registered << item
    end
  end

  return { statusCode: 200, body: { message: 'ok', channel_id: channel_id, count: registered.length, items: registered }.to_json }
end

# For local testing
if $PROGRAM_NAME == __FILE__
  # Local testing uses only environment variables; no CLI args are read.
  # Set CHANNEL_ID or CHANNEL_URL to list uploads, or set VIDEO_ID or URL for a single video.
  #puts 
  handler(event: {})
end
