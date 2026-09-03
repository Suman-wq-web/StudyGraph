/**
 * TypeScript port of the video-id extraction in
 * backend/app/services/ingestion/youtube_transcript.py:extract_video_id --
 * kept behaviorally identical (same recognized URL shapes) so a resource
 * the backend can already fetch a transcript for is exactly the set of
 * resources the frontend can embed a player for. Pure, no network call.
 */

const YOUTUBE_HOSTS = new Set(["youtube.com", "youtu.be", "youtube-nocookie.com"]);

export function extractYoutubeVideoId(url: string | null | undefined): string | null {
  if (!url) return null;

  let parsed: URL;
  try {
    parsed = new URL(url.trim());
  } catch {
    return null;
  }

  let host = parsed.hostname.toLowerCase();
  if (host.startsWith("www.")) host = host.slice(4);
  if (host.startsWith("m.")) host = host.slice(2);
  if (!YOUTUBE_HOSTS.has(host)) return null;

  let candidate: string | null = null;
  if (host === "youtu.be") {
    candidate = parsed.pathname.replace(/^\//, "").split("/")[0] || null;
  } else {
    const queryId = parsed.searchParams.get("v");
    if (queryId) {
      candidate = queryId;
    } else {
      for (const prefix of ["/embed/", "/shorts/", "/live/"]) {
        if (parsed.pathname.startsWith(prefix)) {
          candidate = parsed.pathname.slice(prefix.length).split("/")[0];
          break;
        }
      }
    }
  }

  return candidate || null;
}

const DIRECT_VIDEO_EXTENSIONS = [".mp4", ".webm", ".ogg", ".mov", ".m4v"];

/** Whether `url` looks like a direct playable video file (as opposed to a
 * page that happens to contain a video, e.g. a Vimeo watch page) -- used to
 * decide whether VideoProgressPlayer can fall back to a native <video> tag
 * when it isn't a recognized YouTube link. */
export function looksLikeDirectVideoFile(url: string | null | undefined): boolean {
  if (!url) return false;
  try {
    const { pathname } = new URL(url.trim());
    return DIRECT_VIDEO_EXTENSIONS.some((ext) => pathname.toLowerCase().endsWith(ext));
  } catch {
    return false;
  }
}
