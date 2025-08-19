import { ddb } from './aws';
import {
  ScanCommand,
  GetCommand,
  QueryCommand,
  PutCommand,
  UpdateCommand,
  DeleteCommand,
} from '@aws-sdk/lib-dynamodb';
import { containsNormalized } from './normalize';

export interface VideoRecord {
  video_id: string;
  title: string;
  author: string;
  duration: string;
  views: number;
  description: string;
  url: string;
  transcribed: boolean;
  created_at: string;
  updated_at: string;
}

export class YouTubeDynamoClient {
  constructor(private tableName: string) {}

  async testConnection(): Promise<boolean> {
    try {
      await ddb.send(new ScanCommand({ TableName: this.tableName, Limit: 1 }));
      return true;
    } catch {
      return false;
    }
  }

  // ...existing code...
  async getVideos(
    limit = 50,
    lastEvaluatedKey?: Record<string, any>,
    transcribedFilter?: number,
    videoId?: string
  ) {
    // Try Query on createdAt index (descending) with optional transcribed filter, fallback to Scan
    const items: VideoRecord[] = [];
    let lastKey = lastEvaluatedKey;

    // If a videoId is provided, prefer Query on an index keyed by video_id with sort key createdAt
    if (videoId) {
      const byVidIndex = process.env.YOUTUBE_DYNAMODB_BY_VIDEOID_INDEX; // e.g., 'VideoIdCreatedAtIndex'
      const videoIdAttr = process.env.YOUTUBE_DYNAMODB_VIDEO_ID_ATTR || 'video_id';
      if (byVidIndex) {
        try {
          const names: Record<string, string> = { '#vid': videoIdAttr };
          const values: Record<string, any> = { ':v': videoId };
          const queryParams: any = {
            TableName: this.tableName,
            IndexName: byVidIndex,
            KeyConditionExpression: '#vid = :v',
            ExpressionAttributeNames: names,
            ExpressionAttributeValues: values,
            Limit: limit,
            ExclusiveStartKey: lastKey,
            ScanIndexForward: false, // DESC on sort key (createdAt)
          };
          if (typeof transcribedFilter === 'number') {
            queryParams.FilterExpression = '#t = :tf';
            queryParams.ExpressionAttributeNames['#t'] = 'transcribed';
            queryParams.ExpressionAttributeValues[':tf'] = transcribedFilter;
          }
          const q = await ddb.send(new QueryCommand(queryParams));
          const pageItems = (q.Items || []) as VideoRecord[];
          items.push(...pageItems);
          lastKey = q.LastEvaluatedKey;
          return { videos: items, last_evaluated_key: lastKey, count: items.length };
        } catch (e) {
          console.warn('Query by videoId index failed, falling back to Scan. Error:', e);
          // fall through to Scan fallback below
          // Add a strict equality filter on video_id to minimize scanned items
        }
      }
      // Scan fallback constrained by video_id and optional transcribed
      const baseParamsVid: any = {
        TableName: this.tableName,
        FilterExpression:
          '#vid = :v' + (typeof transcribedFilter === 'number' ? ' AND #t = :tf' : ''),
        ExpressionAttributeNames: { '#vid': videoIdAttr },
        ExpressionAttributeValues: { ':v': videoId },
      };
      if (typeof transcribedFilter === 'number') {
        baseParamsVid.ExpressionAttributeNames['#t'] = 'transcribed';
        baseParamsVid.ExpressionAttributeValues[':tf'] = transcribedFilter;
      }
      while (items.length < limit) {
        const pageLimit = Math.min(limit, limit - items.length);
        const params: any = { ...baseParamsVid, Limit: pageLimit };
        if (lastKey) params.ExclusiveStartKey = lastKey;
        const resp = await ddb.send(new ScanCommand(params));
        const pageItems = (resp.Items || []) as VideoRecord[];
        items.push(...pageItems);
        lastKey = resp.LastEvaluatedKey;
        if (!lastKey) break;
      }
      // Sort by createdAt/created_at descending locally then slice
      const getTsVid = (v: any) => {
        const ts = v?.createdAt || v?.created_at || v?.CreatedAt || v?.updated_at || v?.UpdatedAt;
        const t = ts ? Date.parse(ts) : 0;
        return Number.isFinite(t) && !Number.isNaN(t) ? t : 0;
      };
      items.sort((a, b) => getTsVid(b) - getTsVid(a));
      const slicedVid = items.slice(0, limit);
      return { videos: slicedVid, last_evaluated_key: lastKey, count: slicedVid.length };
    }

    const indexName = process.env.YOUTUBE_DYNAMODB_CREATED_AT_INDEX; // e.g., 'CreatedAtIndex'
    const indexPkName = process.env.YOUTUBE_DYNAMODB_INDEX_PK_NAME; // e.g., 'entity'
    const indexPkValue = process.env.YOUTUBE_DYNAMODB_INDEX_PK_VALUE; // e.g., 'video'

    if (indexName && indexPkName && typeof indexPkValue !== 'undefined') {
      try {
        const names: Record<string, string> = { '#pk': indexPkName };
        const values: Record<string, any> = { ':pkv': indexPkValue };
        const queryParams: any = {
          TableName: this.tableName,
          IndexName: indexName,
          KeyConditionExpression: '#pk = :pkv',
          ExpressionAttributeNames: names,
          ExpressionAttributeValues: values,
          Limit: limit,
          ExclusiveStartKey: lastKey,
          ScanIndexForward: false, // DESC on sort key (createdAt)
        };
        if (typeof transcribedFilter === 'number') {
          queryParams.FilterExpression = '#t = :tf';
          queryParams.ExpressionAttributeNames['#t'] = 'transcribed';
          queryParams.ExpressionAttributeValues[':tf'] = transcribedFilter;
        }
        const q = await ddb.send(new QueryCommand(queryParams));
        const pageItems = (q.Items || []) as VideoRecord[];
        items.push(...pageItems);
        lastKey = q.LastEvaluatedKey;
        return { videos: items, last_evaluated_key: lastKey, count: items.length };
      } catch (e) {
        // fall through to Scan
        console.warn('Query on createdAt index failed, falling back to Scan. Error:', e);
      }
    }

    const baseParams: any = { TableName: this.tableName };
    if (typeof transcribedFilter === 'number') {
      baseParams.FilterExpression = '#t = :tf';
      baseParams.ExpressionAttributeNames = { '#t': 'transcribed' };
      baseParams.ExpressionAttributeValues = { ':tf': transcribedFilter };
    }

    while (items.length < limit) {
      const pageLimit = Math.min(limit, limit - items.length);
      const params: any = { ...baseParams, Limit: pageLimit };
      if (lastKey) params.ExclusiveStartKey = lastKey;

      const resp = await ddb.send(new ScanCommand(params));
      const pageItems = (resp.Items || []) as VideoRecord[];
      items.push(...pageItems);
      lastKey = resp.LastEvaluatedKey;

      if (!lastKey) break; // これ以上データなし
    }

    // Sort by createdAt/created_at descending locally before slicing (Scan has no order)
    const getTs = (v: any) => {
      const ts = v?.createdAt || v?.created_at || v?.CreatedAt || v?.updated_at || v?.UpdatedAt;
      const t = ts ? Date.parse(ts) : 0;
      return Number.isFinite(t) && !Number.isNaN(t) ? t : 0;
    };
    items.sort((a, b) => getTs(b) - getTs(a));
    const sliced = items.slice(0, limit);
    return { videos: sliced, last_evaluated_key: lastKey, count: sliced.length };
  }

  async searchVideos(searchTerm: string, limit = 50, lastEvaluatedKey?: Record<string, any>) {
    // Basic contains via DynamoDB plus local normalization filter (broader scan cap)
    const base = await ddb.send(
      new ScanCommand({
        TableName: this.tableName,
        Limit: limit * 3,
        FilterExpression: 'contains(#ti, :q) OR contains(#au, :q) OR contains(#de, :q)',
        ExpressionAttributeNames: { '#ti': 'title', '#au': 'author', '#de': 'description' },
        ExpressionAttributeValues: { ':q': searchTerm },
        ExclusiveStartKey: lastEvaluatedKey,
      })
    );
    const baseItems = (base.Items || []) as VideoRecord[];

    const broad = await ddb.send(new ScanCommand({ TableName: this.tableName, Limit: limit * 5 }));
    const normalized = ((broad.Items || []) as VideoRecord[]).filter(
      (v: VideoRecord) =>
        containsNormalized(v.title, searchTerm) ||
        containsNormalized(v.author, searchTerm) ||
        containsNormalized(v.description, searchTerm)
    );

    const combined: Record<string, VideoRecord> = {};
    for (const item of [...baseItems, ...normalized]) combined[item.video_id] = item;
    const unique = Object.values(combined).slice(0, limit);

    return {
      videos: unique,
      last_evaluated_key: base.LastEvaluatedKey,
      count: unique.length,
      search_term: searchTerm,
    };
  }

  async getVideoById(video_id: string): Promise<VideoRecord | null> {
    const resp = await ddb.send(new GetCommand({ TableName: this.tableName, Key: { video_id } }));
    if (!resp.Item) return null;
    return resp.Item as VideoRecord;
  }

  async getStats() {
    const total = await ddb.send(new ScanCommand({ TableName: this.tableName, Select: 'COUNT' }));
    const transcribed = await ddb.send(
      new ScanCommand({
        TableName: this.tableName,
        Select: 'COUNT',
        FilterExpression: '#t = :one',
        ExpressionAttributeNames: { '#t': 'transcribed' },
        ExpressionAttributeValues: { ':one': 1 },
      })
    );
    const totalCount = total.Count || 0;
    const transcribedCount = transcribed.Count || 0;
    const untranscribed = totalCount - transcribedCount;
    const percent = totalCount ? Math.round((transcribedCount / totalCount) * 1000) / 10 : 0;
    console.log(
      `Total videos: ${totalCount}, Transcribed videos: ${transcribedCount}, Untranscribed videos: ${untranscribed}, Transcription percentage: ${percent}%`
    );
    return {
      total_videos: totalCount,
      transcribed_videos: transcribedCount,
      untranscribed_videos: untranscribed,
      transcription_percentage: percent,
    };
  }
}
