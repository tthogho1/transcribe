import { NextRequest, NextResponse } from 'next/server';
import { s3 } from '../../../../../src/aws';
import { GetObjectCommand, PutObjectCommand } from '@aws-sdk/client-s3';

const bucket = process.env.S3_BUCKET_NAME;

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  try {
    if (!bucket)
      return NextResponse.json({ error: 'S3 configuration not available' }, { status: 500 });
    // const key = `${params.id}.json`;
    const key = `${params.id}_transcription.json`;
    const out = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: key }));
    const body = await (out.Body as any).transformToString();
    return NextResponse.json({
      video_id: params.id,
      transcription: body,
      s3_bucket: bucket,
      s3_key: key,
      last_modified: (out.LastModified as Date | undefined)?.toISOString() || null,
      content_length: out.ContentLength || 0,
    });
  } catch (e: any) {
    const msg = e?.name === 'NoSuchKey' ? 'Transcription file not found' : e.message || String(e);
    return NextResponse.json({ error: msg }, { status: e?.name === 'NoSuchKey' ? 404 : 500 });
  }
}

export async function PUT(req: NextRequest, { params }: { params: { id: string } }) {
  try {
    if (!bucket)
      return NextResponse.json({ error: 'S3 configuration not available' }, { status: 500 });

    const key = `${params.id}_transcription.json`;
    const body = await req.text();

    if (!body) {
      return NextResponse.json({ error: 'Request body is empty' }, { status: 400 });
    }

    await s3.send(
      new PutObjectCommand({
        Bucket: bucket,
        Key: key,
        Body: body,
        ContentType: 'application/json',
      })
    );

    return NextResponse.json({
      success: true,
      video_id: params.id,
      s3_bucket: bucket,
      s3_key: key,
      message: 'Transcription updated successfully',
    });
  } catch (e: any) {
    const msg = e.message || String(e);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
