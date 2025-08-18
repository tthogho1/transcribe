import { NextRequest, NextResponse } from 'next/server';
import { YouTubeDynamoClient } from '../../../../src/dynamoClient';

const tableName = process.env.YOUTUBE_DYNAMODB_TABLE || 'youtube_videos';
const client = new YouTubeDynamoClient(tableName);

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const limit = Math.min(parseInt(String(searchParams.get('limit') || 50), 10) || 50, 100);
    const lastKeyParam = String(searchParams.get('last_key') || '');
    let lastEvaluatedKey: any = undefined;
    if (lastKeyParam) {
      try {
        const decoded = Buffer.from(lastKeyParam, 'base64').toString('utf-8');
        lastEvaluatedKey = JSON.parse(decoded);
      } catch {}
    }
    const result = await client.getVideos(limit, lastEvaluatedKey, 0);
    if ((result as any).last_evaluated_key) {
      const encoded = Buffer.from(
        JSON.stringify((result as any).last_evaluated_key),
        'utf-8'
      ).toString('base64');
      (result as any).next_page_key = encoded;
      delete (result as any).last_evaluated_key;
    }
    return NextResponse.json(result);
  } catch (e: any) {
    return NextResponse.json({ error: e.message || String(e) }, { status: 500 });
  }
}
