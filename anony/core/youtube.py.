# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import os
import re
import asyncio
import aiohttp
import yt_dlp
from pathlib import Path, PurePosixPath

from py_yt import VideosSearch, Playlist

from anony import config, logger
from anony.helpers import Track, utils


class NexGenApi:
    def __init__(
            self, api_url: str, video_api_url: str, api_key: str,
            retries: int = 10, timeout: int = 40,
        ):
        self.api_url = api_url
        self.video_api_url = video_api_url
        self.api_key = api_key
        self.chunk_limit = 128 * 1024
        self.dl_cache = {}
        self.v_cache = {}
        self.retries = retries
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: aiohttp.ClientSession | None = None
        self.headers = {"Accept": "application/json"}

    async def get_session(self) -> None:
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
            logger.info("NexGenApi: aiohttp session created.")

    @staticmethod
    def _safe_filename(name: str) -> str:
        name = PurePosixPath(name).name
        name = re.sub(r"[^\w.\-]", "_", name)
        if not name or name.startswith("."):
            name = "download"
        return name

    async def save_file(self, vid_id: str, url: str, video: bool = False) -> str | None:
        safe_vid_id = self._safe_filename(vid_id)
        logger.info(f"NexGenApi.save_file: Downloading file for vid_id={vid_id!r}, video={video}, url={url!r}")
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"NexGenApi.save_file: HTTP {resp.status} while downloading file for {vid_id!r}")
                    return None
                file_name = None
                cd = resp.headers.get("Content-Disposition")
                if cd:
                    match = re.search(r'filename="?(.+?)"?$', cd)
                    if match:
                        file_name = self._safe_filename(match.group(1))
                if not file_name:
                    file_name = safe_vid_id + (".mp4" if video else ".mp3")
                fname = f"downloads/{file_name}"
                logger.info(f"NexGenApi.save_file: Saving to {fname!r}")
                with open(fname, "wb") as f:
                    async for chunk in resp.content.iter_chunked(self.chunk_limit):
                        if chunk:
                            f.write(chunk)
                if video:
                    self.v_cache[vid_id] = fname
                else:
                    self.dl_cache[vid_id] = fname
                logger.info(f"NexGenApi.save_file: Successfully saved {fname!r}")
                return fname
        except Exception as ex:
            logger.error(f"NexGenApi.save_file: Exception for vid_id={vid_id!r}: {ex}")
        return None

    async def download(self, vid_id: str, video: bool = False) -> str | None:
        if video and vid_id in self.v_cache:
            logger.info(f"NexGenApi.download: Cache hit (video) for {vid_id!r}")
            return self.v_cache[vid_id]
        elif not video and vid_id in self.dl_cache:
            logger.info(f"NexGenApi.download: Cache hit (audio) for {vid_id!r}")
            return self.dl_cache[vid_id]

        endp = f"{self.api_url}/song/{vid_id}?api={self.api_key}"
        if video:
            endp = f"{self.video_api_url}/video/{vid_id}?api={self.api_key}"

        logger.info(f"NexGenApi.download: Requesting endpoint={endp!r}, video={video}")
        await self.get_session()

        for attempt in range(self.retries):
            try:
                async with self.session.get(endp, headers=self.headers) as resp:
                    data = await resp.json()
                    logger.info(f"NexGenApi.download: attempt={attempt+1}, HTTP={resp.status}, response={data}")
                    if resp.status != 200:
                        logger.warning(f"NexGenApi.download: Non-200 status {resp.status} for {vid_id!r}")
                        return None
                    status = data.get("status")
                    dl_link = data.get("link")
                    if not status:
                        logger.warning(f"NexGenApi.download: No 'status' in response for {vid_id!r}: {data}")
                        return None
                    if status == "done":
                        if not dl_link:
                            logger.warning(f"NexGenApi.download: status=done but no 'link' for {vid_id!r}")
                            return None
                        return await self.save_file(vid_id, dl_link, video)
                    elif status == "downloading":
                        logger.info(f"NexGenApi.download: Still downloading, attempt {attempt+1}/{self.retries}, sleeping 4s...")
                        await asyncio.sleep(4)
                        continue
                    else:
                        logger.warning(f"NexGenApi.download: Unknown status={status!r} for {vid_id!r}")
                        break
            except Exception as ex:
                logger.error(f"NexGenApi.download: Exception on attempt {attempt+1} for {vid_id!r}: {ex}")
                break

        logger.warning(f"NexGenApi.download: All retries exhausted for {vid_id!r}, returning None")
        return None


class YouTube:
    def __init__(self):
        self.api = None
        self.base = "https://www.youtube.com/watch?v="
        self.cookie_dir = "anony/cookies"
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        self.iregex = re.compile(
            r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)"
            r"(?!/(watch\?v=[A-Za-z0-9_-]{11}|shorts/[A-Za-z0-9_-]{11}"
            r"|playlist\?list=PL[A-Za-z0-9_-]+|[A-Za-z0-9_-]{11}))\S*"
        )
        if config.API_URL and config.VIDEO_API_URL and config.API_KEY:
            self.api = NexGenApi(config.API_URL, config.VIDEO_API_URL, config.API_KEY)
            logger.info(f"YouTube: NexGenApi initialized. api_url={config.API_URL!r}, video_api_url={config.VIDEO_API_URL!r}")
        else:
            logger.warning("YouTube: NexGenApi NOT initialized — API_URL, VIDEO_API_URL or API_KEY missing in config.")

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def invalid(self, url: str) -> bool:
        return bool(re.match(self.iregex, url))

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("YouTube.save_cookies: Saving cookies from urls...")
        async with aiohttp.ClientSession() as session:
            for url in urls:
                raw_name = url.split("/")[-1]
                name = re.sub(r"[^\w\-]", "", raw_name)
                if not name:
                    logger.warning(f"YouTube.save_cookies: Skipping invalid cookie URL: {url}")
                    continue
                link = "https://batbin.me/raw/" + name
                async with session.get(link) as resp:
                    resp.raise_for_status()
                    with open(f"{self.cookie_dir}/{name}.txt", "wb") as fw:
                        fw.write(await resp.read())
        logger.info(f"YouTube.save_cookies: Cookies saved in {self.cookie_dir}.")

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        logger.info(f"YouTube.search: query={query!r}, video={video}")
        try:
            _search = VideosSearch(query, limit=1)
            results = await _search.next()
            if results and results.get("result"):
                data = results["result"][0]
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name"),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    message_id=m_id,
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails", [{}])[-1].get("url", "").split("?")[0],
                    url=data.get("link"),
                    view_count=data.get("viewCount", {}).get("short"),
                    video=video,
                )
                logger.info(f"YouTube.search: Found — id={track.id!r}, title={track.title!r}, duration={track.duration!r}")
                return track
            else:
                logger.warning(f"YouTube.search: No results found for query={query!r}")
        except Exception as ex:
            logger.error(f"YouTube.search: Exception for query={query!r}: {ex}")
        return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        logger.info(f"YouTube.playlist: url={url!r}, limit={limit}, video={video}")
        tracks = []
        try:
            plist = await Playlist.get(url)
            videos = plist.get("videos", [])[:limit]
            logger.info(f"YouTube.playlist: Got {len(videos)} tracks from playlist")
            for data in videos:
                track = Track(
                    id=data.get("id"),
                    channel_name=data.get("channel", {}).get("name", ""),
                    duration=data.get("duration"),
                    duration_sec=utils.to_seconds(data.get("duration")),
                    title=data.get("title")[:25],
                    thumbnail=data.get("thumbnails", [{}])[-1].get("url", "").split("?")[0],
                    url=data.get("link", "").split("&list=")[0],
                    user=user,
                    view_count="",
                    video=video,
                )
                tracks.append(track)
        except Exception as ex:
            logger.error(f"YouTube.playlist: Exception for url={url!r}: {ex}")
        return tracks

    @staticmethod
    def _sanitize_video_id(video_id: str) -> str | None:
        video_id = video_id.strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return video_id
        if re.fullmatch(r"PL[A-Za-z0-9_-]+", video_id):
            return video_id
        return None

    async def download(self, video_id: str, video: bool = False) -> str | None:
        logger.info(f"YouTube.download: video_id={video_id!r}, video={video}")

        safe_id = self._sanitize_video_id(video_id)
        if not safe_id:
            logger.warning(f"YouTube.download: Blocked suspicious video_id={video_id!r}")
            return None
        video_id = safe_id

        # Audio — sirf NexGen API, koi fallback nahi
        if not video:
            if not self.api:
                logger.error("YouTube.download: NexGenApi not initialized, cannot download audio.")
                return None
            logger.info(f"YouTube.download: Trying NexGenApi for audio, video_id={video_id!r}")
            file_path = await self.api.download(video_id, video=False)
            if file_path:
                logger.info(f"YouTube.download: NexGenApi success — {file_path!r}")
                return file_path
            logger.error(f"YouTube.download: NexGenApi failed for audio {video_id!r}, no fallback.")
            return None

        # Video — yt-dlp (no cookies, IP risk low for video only)
        logger.info(f"YouTube.download: video=True, using yt-dlp for {video_id!r}")
        url = self.base + video_id
        filename = f"downloads/{video_id}.mp4"

        if Path(filename).exists():
            logger.info(f"YouTube.download: yt-dlp cache hit — {filename!r}")
            return filename

        ydl_opts = {
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": True,
            "overwrites": False,
            "nocheckcertificate": True,
            "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)",
            "merge_output_format": "mp4",
        }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as ex:
                    logger.error(f"YouTube.download: yt-dlp DownloadError for {url!r}: {ex}")
                    return None
                except Exception as ex:
                    logger.error(f"YouTube.download: yt-dlp unexpected error for {url!r}: {ex}")
                    return None
            logger.info(f"YouTube.download: yt-dlp success — {filename!r}")
            return filename

        return await asyncio.to_thread(_download)
