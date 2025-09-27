import { NextRequest, NextResponse } from 'next/server';
import { S3Client, GetObjectCommand } from '@aws-sdk/client-s3';

// AWS S3の設定
const s3Client = new S3Client({
  credentials: {
    accessKeyId: process.env.AWS_ACCESS_KEY_ID!,
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY!,
  },
  region: process.env.AWS_REGION || 'ap-northeast-1',
});

export async function GET(request: NextRequest, { params }: { params: { id: string } }) {
  try {
    const { id } = params;
    const bucketName = process.env.S3_BUCKET_NAME || 'audio4gladia';
    const key = `${id}_transcription.json`;

    // S3からファイルを取得
    const command = new GetObjectCommand({
      Bucket: bucketName,
      Key: key,
    });

    const response = await s3Client.send(command);

    if (!response.Body) {
      return NextResponse.json({ error: 'File not found' }, { status: 404 });
    }

    // ファイル内容を取得
    const fileContent = await response.Body.transformToString();

    // レスポンスヘッダーを設定してファイルダウンロード
    return new NextResponse(fileContent, {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Content-Disposition': `attachment; filename="${id}_transcription.json"`,
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      },
    });
  } catch (error) {
    console.error('Download error:', error);

    if ((error as AWS.AWSError).code === 'NoSuchKey') {
      return NextResponse.json({ error: 'Transcription file not found' }, { status: 404 });
    }

    return NextResponse.json({ error: 'Failed to download file' }, { status: 500 });
  }
}
