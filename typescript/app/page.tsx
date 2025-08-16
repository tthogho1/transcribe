'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

type VideoRecord = {
  video_id: string;
  title?: string;
  author?: string;
  duration?: string;
  views?: number;
  description?: string;
  url?: string;
  transcribed?: boolean;
  created_at?: string;
  updated_at?: string;
};

type Stats = {
  total_videos: number;
  transcribed_videos: number;
  untranscribed_videos: number;
  transcription_percentage: number;
};

export default function HomePage() {
  // Global state
  const [currentFilter, setCurrentFilter] = useState<'all' | 'transcribed' | 'untranscribed'>(
    'all'
  );
  const [currentSearchTerm, setCurrentSearchTerm] = useState<string>('');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [nextPageKey, setNextPageKey] = useState<string | null>(null);
  const [previousPageKeys, setPreviousPageKeys] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState<string>('');

  const titleText = useMemo(() => {
    if (currentSearchTerm) return `Search Results: "${currentSearchTerm}"`;
    if (currentFilter === 'transcribed') return 'Transcribed Videos';
    if (currentFilter === 'untranscribed') return 'Untranscribed Videos';
    return 'All Videos';
  }, [currentFilter, currentSearchTerm]);

  // Effects
  useEffect(() => {
    loadStats();
    // initial list
    loadVideos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Filter change reloading videos
  useEffect(() => {
    loadVideos(null);
  }, [currentFilter]);

  // API calls
  const loadStats = useCallback(async () => {
    try {
      const resp = await fetch('/api/stats', { cache: 'no-store' });
      const data = await resp.json();
      if (resp.ok) {
        setStats(data.stats);
      } else {
        console.error('Failed to load stats:', data.error);
      }
    } catch (e: any) {
      console.error('Error loading stats:', e);
    }
  }, []);

  const buildVideosUrl = useCallback(
    (lastKey?: string | null) => {
      const limit = 50;
      let url = '/api/videos?limit=50';
      if (currentFilter === 'transcribed') url = '/api/videos/transcribed?limit=50';
      if (currentFilter === 'untranscribed') url = '/api/videos/untranscribed?limit=50';
      if (currentSearchTerm)
        url = `/api/search?q=${encodeURIComponent(currentSearchTerm)}&limit=${limit}`;
      if (lastKey) url += `&last_key=${encodeURIComponent(lastKey)}`;
      return url;
    },
    [currentFilter, currentSearchTerm]
  );

  const loadVideos = useCallback(
    async (lastKey?: string | null) => {
      if (isLoading) return;
      setIsLoading(true);
      setError('');
      try {
        const url = buildVideosUrl(lastKey || undefined);
        const resp = await fetch(url, { cache: 'no-store' });
        const data = await resp.json();
        if (resp.ok) {
          setVideos(data.videos || []);
          setNextPageKey(data.next_page_key || null);
        } else {
          setError(data.error || 'Failed to load videos');
        }
      } catch (e: any) {
        setError(`Error loading videos: ${e?.message || String(e)}`);
      } finally {
        setIsLoading(false);
      }
    },
    [buildVideosUrl, isLoading]
  );

  // UI handlers
  const handleSetFilter = useCallback(
    (filter: 'all' | 'transcribed' | 'untranscribed') => {
      setCurrentFilter(filter);
      setCurrentPage(1);
      setNextPageKey(null);
      setPreviousPageKeys([]);
      // When searching, clear the term if user switches filters
      if (currentSearchTerm) setCurrentSearchTerm('');
      // void loadVideos(null);
    },
    [currentSearchTerm, loadVideos]
  );

  const handleSearch = useCallback(() => {
    setCurrentPage(1);
    setNextPageKey(null);
    setPreviousPageKeys([]);
    if (!currentSearchTerm.trim()) {
      // reset to all
      setCurrentFilter('all');
      void loadVideos(null);
    } else {
      // clear filter to all and execute search
      setCurrentFilter('all');
      void loadVideos(null);
    }
  }, [currentSearchTerm, loadVideos]);

  const clearSearch = useCallback(() => {
    setCurrentSearchTerm('');
    handleSetFilter('all');
  }, [handleSetFilter]);

  const refreshData = useCallback(() => {
    setCurrentPage(1);
    setNextPageKey(null);
    setPreviousPageKeys([]);
    void loadStats();
    void loadVideos(null);
    setSuccess('Data refreshed successfully');
    setTimeout(() => setSuccess(''), 3000);
  }, [loadStats, loadVideos]);

  const nextPage = useCallback(() => {
    if (!nextPageKey || isLoading) return;
    setPreviousPageKeys(prev => [...prev, nextPageKey]);
    setCurrentPage(p => p + 1);
    void loadVideos(nextPageKey);
  }, [isLoading, loadVideos, nextPageKey]);

  const previousPage = useCallback(() => {
    if (currentPage === 1 || isLoading) return;
    setCurrentPage(p => Math.max(1, p - 1));
    setPreviousPageKeys(prev => {
      const copy = [...prev];
      copy.pop();
      const last = copy.length > 0 ? copy[copy.length - 1] : null;
      void loadVideos(last);
      return copy;
    });
  }, [currentPage, isLoading, loadVideos]);

  const formatDuration = (duration?: string) => {
    if (!duration) return 'Unknown';
    return duration.replace('PT', '').replace('M', ':').replace('S', '');
  };

  const formatNumber = (num?: number) => {
    if (!num) return '0';
    if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + 'M';
    if (num >= 1_000) return (num / 1_000).toFixed(1) + 'K';
    return String(num);
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Unknown';
    try {
      const d = new Date(dateString);
      return d.toLocaleDateString();
    } catch {
      return 'Invalid Date';
    }
  };

  const viewTranscription = (videoId: string) => {
    const url = `/transcription/${videoId}`;
    const windowName = `transcription_${videoId}`;
    const features = 'width=1000,height=800,scrollbars=yes,resizable=yes,menubar=no,toolbar=no';
    window.open(url, windowName, features);
  };

  return (
    <div>
      <div className="container-max">
        <div className="bg-gradient-to-r from-indigo-500 to-purple-600 text-white p-8 mb-8 rounded-lg shadow-md">
          <h1 className="m-0 text-4xl font-light">YouTube Video Management</h1>
          <p className="mt-2 text-lg opacity-90">
            Manage and view YouTube video transcription data
          </p>
        </div>

        {/* Stats */}
        <div id="stats" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {stats ? (
            <>
              <div className="card p-6 text-center">
                <div className="text-3xl font-bold text-indigo-500 mb-2">
                  {stats.total_videos || 0}
                </div>
                <div className="text-gray-500 text-sm uppercase tracking-wide">Total Videos</div>
              </div>
              <div className="card p-6 text-center">
                <div className="text-3xl font-bold text-indigo-500 mb-2">
                  {stats.transcribed_videos || 0}
                </div>
                <div className="text-gray-500 text-sm uppercase tracking-wide">Transcribed</div>
              </div>
              <div className="card p-6 text-center">
                <div className="text-3xl font-bold text-indigo-500 mb-2">
                  {stats.untranscribed_videos || 0}
                </div>
                <div className="text-gray-500 text-sm uppercase tracking-wide">Untranscribed</div>
              </div>
              <div className="card p-6 text-center">
                <div className="text-3xl font-bold text-indigo-500 mb-2">
                  {Math.round(stats.transcription_percentage || 0)}%
                </div>
                <div className="text-gray-500 text-sm uppercase tracking-wide">Completion Rate</div>
              </div>
            </>
          ) : (
            <div className="card p-6 text-center col-span-full">Loading stats...</div>
          )}
        </div>

        {/* Controls */}
        <div className="card p-6 mb-8">
          <div className="flex flex-wrap items-center gap-4 mb-4">
            <div className="flex-1 min-w-[300px]">
              <input
                type="text"
                placeholder="Search videos by title or author..."
                value={currentSearchTerm}
                className="w-full rounded-md border-2 border-gray-200 px-3 py-2 text-base focus:outline-none focus:border-indigo-500"
                onChange={e => setCurrentSearchTerm(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleSearch();
                }}
              />
            </div>
            <button className="btn btn-primary" onClick={handleSearch}>
              Search
            </button>
            <button className="btn btn-outline" onClick={clearSearch}>
              Clear
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex gap-2">
              <button
                className={`btn btn-outline ${
                  currentFilter === 'all' ? 'bg-indigo-500 text-white' : ''
                }`}
                onClick={() => handleSetFilter('all')}
              >
                All Videos
              </button>
              <button
                className={`btn btn-outline ${
                  currentFilter === 'transcribed' ? 'bg-indigo-500 text-white' : ''
                }`}
                onClick={() => handleSetFilter('transcribed')}
              >
                Transcribed
              </button>
              <button
                className={`btn btn-outline ${
                  currentFilter === 'untranscribed' ? 'bg-indigo-500 text-white' : ''
                }`}
                onClick={() => handleSetFilter('untranscribed')}
              >
                Untranscribed
              </button>
            </div>
            <button className="btn btn-secondary" onClick={refreshData}>
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div
            className="rounded-md border border-red-200 bg-red-100 text-red-800 p-4 mb-4"
            role="alert"
          >
            {error}
          </div>
        )}
        {success && (
          <div
            className="rounded-md border border-green-200 bg-green-100 text-green-800 p-4 mb-4"
            role="status"
          >
            {success}
          </div>
        )}

        <div className="card overflow-hidden">
          <div className="flex items-center justify-between bg-gray-50 px-6 py-4 border-b border-gray-200">
            <h3 id="videos-title" className="text-lg font-semibold">
              {titleText}
            </h3>
            <span id="video-count" className="text-sm text-gray-500">
              {isLoading ? 'Loading...' : `${videos.length} videos`}
            </span>
          </div>

          <div id="videos-list">
            {isLoading ? (
              <div className="text-center text-gray-500 p-8">Loading videos...</div>
            ) : videos.length === 0 ? (
              <div className="text-center text-gray-500 p-8">No videos found</div>
            ) : (
              videos.map(video => {
                const transcribedTag = video.transcribed ? (
                  <span className="tag tag-transcribed">Transcribed</span>
                ) : (
                  <span className="tag tag-untranscribed">Not Transcribed</span>
                );
                const youtubeUrl = `https://www.youtube.com/watch?v=${video.video_id}`;
                const description = video.description
                  ? video.description.length > 200
                    ? video.description.substring(0, 200) + '...'
                    : video.description
                  : 'No description available';
                return (
                  <div
                    key={video.video_id}
                    className="px-6 py-4 border-b border-gray-200 hover:bg-gray-50 transition-colors"
                  >
                    <div className="font-semibold mb-2 text-gray-800">
                      <a
                        href={youtubeUrl}
                        target="_blank"
                        className="text-red-600 hover:underline"
                        rel="noreferrer"
                      >
                        {video.title || 'Untitled'}
                      </a>
                    </div>
                    <div className="flex flex-col sm:flex-row gap-1 sm:gap-4 text-sm text-gray-500 mb-2">
                      <span>
                        <strong>Author:</strong> {video.author || 'Unknown'}
                      </span>
                      <span>
                        <strong>Duration:</strong> {formatDuration(video.duration)}
                      </span>
                      <span>
                        <strong>Views:</strong> {formatNumber(video.views)}
                      </span>
                      <span>
                        <strong>Published:</strong> {formatDate(video.created_at)}
                      </span>
                    </div>
                    <div className="text-gray-700 mb-2 leading-relaxed">{description}</div>
                    <div className="flex flex-wrap gap-2">
                      {transcribedTag}
                      <button
                        className="tag bg-blue-50 text-blue-700 border border-blue-700 cursor-pointer"
                        title="Click to view transcription"
                        onClick={() => viewTranscription(video.video_id)}
                      >
                        📄 ID: {video.video_id}
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Pagination */}
          {videos.length > 0 && (
            <div
              id="pagination"
              className="flex justify-center items-center gap-4 px-6 py-6 bg-gray-50"
            >
              <button
                className="btn btn-outline disabled:opacity-50"
                id="prevBtn"
                onClick={previousPage}
                disabled={currentPage === 1 || isLoading}
              >
                Previous
              </button>
              <span id="page-info" className="text-sm text-gray-500">
                Page {currentPage}
              </span>
              <button
                className="btn btn-outline disabled:opacity-50"
                id="nextBtn"
                onClick={nextPage}
                disabled={!nextPageKey || isLoading}
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
