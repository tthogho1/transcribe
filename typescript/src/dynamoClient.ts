import { ddb } from './aws';
import { ScanCommand, GetCommand, QueryCommand } from '@aws-sdk/lib-dynamodb';
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
  async getVideos(limit = 50, lastEvaluatedKey?: Record<string, any>, transcribedFilter?: number) {
    const items: VideoRecord[] = [];
    let lastKey = lastEvaluatedKey;

    // Query by transcribed-created_at-index if transcribedFilter is set
    if (typeof transcribedFilter === 'number') {
      try {
        console.log('Querying transcribed-created_at-index with filter:', transcribedFilter);
        const q = await ddb.send(
          new QueryCommand({
            TableName: this.tableName,
            IndexName: 'transcribed-created_at-index',
            KeyConditionExpression: '#t = :tf',
            ExpressionAttributeNames: { '#t': 'transcribed' },
            ExpressionAttributeValues: { ':tf': transcribedFilter },
            Limit: limit,
            ExclusiveStartKey: lastKey,
            ScanIndexForward: false, // DESC
          })
        );
        const pageItems = (q.Items || []) as VideoRecord[];
        items.push(...pageItems);
        lastKey = q.LastEvaluatedKey;
        return { videos: items, last_evaluated_key: lastKey, count: items.length };
      } catch (e) {
        console.warn('Query on transcribed-created_at-index failed, falling back to Scan.', e);
        // fall through to Scan
      }
    } else {
      try {
        console.log('Querying FORALL-created_at-index with filter:', transcribedFilter);
        const q = await ddb.send(
          new QueryCommand({
            TableName: this.tableName,
            IndexName: 'FORALL-created_at-index',
            KeyConditionExpression: '#t = :tf',
            ExpressionAttributeNames: { '#t': 'FORALL' },
            ExpressionAttributeValues: { ':tf': 'A' },
            Limit: limit,
            ExclusiveStartKey: lastKey,
            ScanIndexForward: false, // DESC
          })
        );
        const pageItems = (q.Items || []) as VideoRecord[];
        items.push(...pageItems);
        lastKey = q.LastEvaluatedKey;
        return { videos: items, last_evaluated_key: lastKey, count: items.length };
      } catch (e) {
        console.warn('Query on transcribed-created_at-index failed, falling back to Scan.', e);
        // fall through to Scan
      }
    }
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

    // embedding属性のカウントを取得
    const embeddingTrue = await ddb.send(
      new ScanCommand({
        TableName: this.tableName,
        Select: 'COUNT',
        FilterExpression: '#e = :true',
        ExpressionAttributeNames: { '#e': 'embedding' },
        ExpressionAttributeValues: { ':true': true },
      })
    );

    const embeddingFalse = await ddb.send(
      new ScanCommand({
        TableName: this.tableName,
        Select: 'COUNT',
        FilterExpression: '#e = :false',
        ExpressionAttributeNames: { '#e': 'embedding' },
        ExpressionAttributeValues: { ':false': false },
      })
    );

    const totalCount = total.Count || 0;
    const transcribedCount = transcribed.Count || 0;
    const untranscribed = totalCount - transcribedCount;
    const percent = totalCount ? Math.round((transcribedCount / totalCount) * 1000) / 10 : 0;

    const embeddingTrueCount = embeddingTrue.Count || 0;
    const embeddingFalseCount = embeddingFalse.Count || 0;
    const embeddingTotalCount = embeddingTrueCount + embeddingFalseCount;
    const embeddingPercent = totalCount
      ? Math.round((embeddingTrueCount / totalCount) * 1000) / 10
      : 0;

    console.log(
      `Total videos: ${totalCount}, Transcribed videos: ${transcribedCount}, Untranscribed videos: ${untranscribed}, Transcription percentage: ${percent}%`
    );
    console.log(
      `Embedding True: ${embeddingTrueCount}, Embedding False: ${embeddingFalseCount}, Embedding Total: ${embeddingTotalCount}, Embedding percentage: ${embeddingPercent}%`
    );

    return {
      total_videos: totalCount,
      transcribed_videos: transcribedCount,
      untranscribed_videos: untranscribed,
      transcription_percentage: percent,
      embedding_true: embeddingTrueCount,
      embedding_false: embeddingFalseCount,
      embedding_total: embeddingTotalCount,
      embedding_percentage: embeddingPercent,
    };
  }
}
