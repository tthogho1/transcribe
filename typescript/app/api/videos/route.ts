import { NextRequest, NextResponse } from 'next/server';
import { YouTubeDynamoClient } from '../../../src/dynamoClient';

const tableName = process.env.YOUTUBE_DYNAMODB_TABLE || 'youtube_videos';
const client = new YouTubeDynamoClient(tableName);

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const limit = Math.min(parseInt(String(searchParams.get('limit') || 50), 10) || 50, 100);
    const lastKeyParam = String(searchParams.get('last_key') || '');
    const transcribedParam = searchParams.get('transcribed') || undefined;
    const searchTerm = String(searchParams.get('search') || '').trim();

    let lastEvaluatedKey: any = undefined;
    if (lastKeyParam) {
      try {
        const decoded = Buffer.from(lastKeyParam, 'base64').toString('utf-8');
        lastEvaluatedKey = JSON.parse(decoded);
      } catch {}
    }

    let transcribedFilter: boolean | undefined = undefined;
    if (typeof transcribedParam === 'string') {
      transcribedFilter = transcribedParam.toLowerCase() === 'true';
    }

    let result;
    if (searchTerm) {
      result = await client.searchVideos(searchTerm, limit, lastEvaluatedKey);
    } else {
      result = await client.getVideos(limit, lastEvaluatedKey, transcribedFilter);
    }

    if ((result as any).last_evaluated_key) {
      const encoded = Buffer.from(
        JSON.stringify((result as any).last_evaluated_key),
        'utf-8'
      ).toString('base64');
      (result as any).next_page_key = encoded;
      delete (result as any).last_evaluated_key;
    }

    (result as any).request_params = {
      limit,
      transcribed_filter: transcribedFilter ?? null,
      search_term: searchTerm || null,
    };

    return NextResponse.json(result);
  } catch (e: any) {
    return NextResponse.json({ error: e.message || String(e) }, { status: 500 });
  }
}
