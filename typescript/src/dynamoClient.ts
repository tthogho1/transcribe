import { ddb } from './aws';
import {
  ScanCommand,
  GetCommand,
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
  async getVideos(limit = 50, lastEvaluatedKey?: Record<string, any>, transcribedFilter?: boolean) {
    const baseParams: any = { TableName: this.tableName };
    if (typeof transcribedFilter === 'boolean') {
      baseParams.FilterExpression = '#t = :tf';
      baseParams.ExpressionAttributeNames = { '#t': 'transcribed' };
      baseParams.ExpressionAttributeValues = { ':tf': transcribedFilter };
    }

    const items: VideoRecord[] = [];
    let lastKey = lastEvaluatedKey;

    while (items.length < limit) {
      // 1回あたりの読み取り上限（大きめにして往復回数を削減）
      const pageLimit = Math.min(1000, Math.max(100, limit - items.length));
      const params: any = { ...baseParams, Limit: pageLimit };
      if (lastKey) params.ExclusiveStartKey = lastKey;

      const resp = await ddb.send(new ScanCommand(params));
      const pageItems = (resp.Items || []) as VideoRecord[];
      items.push(...pageItems);
      lastKey = resp.LastEvaluatedKey;

      if (!lastKey) break; // これ以上データなし
    }

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
        FilterExpression: '#t = :true',
        ExpressionAttributeNames: { '#t': 'transcribed' },
        ExpressionAttributeValues: { ':true': true },
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
