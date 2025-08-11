'use client';
import { useState } from 'react';

export default function EditableArea({ id, initialValue }: { id: string; initialValue: string }) {
  const [value, setValue] = useState<string>(initialValue);
  const [copied, setCopied] = useState(false);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error('Copy failed', e);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <button className="btn btn-secondary" onClick={copyToClipboard}>
          {copied ? 'Copied!' : 'Copy'}
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
