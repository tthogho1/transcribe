'use client';
import { useState } from 'react';

export default function EditableArea({ id, initialValue }: { id: string; initialValue: string }) {
  const [value, setValue] = useState<string>(initialValue);
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error('Copy failed', e);
    }
  };

  const downloadFile = async () => {
    try {
      setDownloading(true);
      // Content-Dispositionヘッダーが設定されているので、直接リンクでダウンロード可能
      const a = document.createElement('a');
      a.href = `/api/videos/${id}/download`;
      a.download = `${id}_transcription.json`; // フォールバック用
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (error) {
      console.error('Download error:', error);
      alert('ダウンロードに失敗しました');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <button className="btn btn-secondary" onClick={copyToClipboard}>
          {copied ? 'Copied!' : 'Copy'}
        </button>
        <button className="btn btn-primary" onClick={downloadFile} disabled={downloading}>
          {downloading ? 'Downloading...' : 'Download'}
        </button>
        <a
          href={`/api/videos/${id}/transcription`}
          target="_blank"
          rel="noreferrer"
          className="btn btn-outline"
        >
          Open raw
        </a>
      </div>
      <textarea
        className="w-full h-[70vh] rounded-md border border-gray-300 p-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        value={value}
        onChange={e => setValue(e.target.value)}
      />
    </div>
  );
}
