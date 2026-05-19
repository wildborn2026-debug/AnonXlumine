# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import os
import re
import asyncio
import aiohttp
import aiofiles
import random
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

    @staticmethod
    def _safe_filename(name: str) -> str:
        name = PurePosixPath(name).name
        name = re.sub(r"[^\w.\-]", "_", name)
        if not name or name.startswith("."):
            name = "download"
        return name

    async def save_file(self, vid_id: str, url: str, video: bool = False) -> str | None:
        safe_vid_id = self._safe_filename(vid_id)
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
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
                async with aiofiles.open(fname, "wb") as f:
                    async for chunk in resp.content.iter_chunked(self.chunk_limit):
                        if chunk:
                            await f.write(chunk)
                if video:
                    self.v_cache[vid_id] = fname
                else:
                    self.dl_cache[vid_id] = fname
                return fname
        except Exception:
            pass
        return None

    async def download(self, vid_id: str, video: bool = False) -> str | None:
        if video and vid_id in self.v_cache:
            return self.v_cache[vid_id]
        elif not video and vid_id in self.dl_cache:
            return self.dl_cache[vid_id]

        endp = f"{self.api_url}/song/{vid_id}?api={self.api_key}"
        if video:
            endp = f"{self.video_api_url}/video/{vid_id}?api={self.api_key}"

        await self.get_session()
        for _ in range(self.retries):
            try:
                async with self.session.get(endp, headers=self.headers) as resp:
                    data = await resp.json()
                    if resp.status != 200:
                        return None
                    status = data.get("status")
                    dl_link = data.get("link")
                    if not status:
                        return None
                    if status == "done":
                        if not dl_link:
                            return None
                        return await self.save_file(vid_id, dl_link, video)
                    elif status == "downloading":
                        await asyncio.sleep(4)
                        continue
                    else:
                        break
            except Exception:
                break
        return None


class YouTube:
    def __init__(self):
        self.api = None
        self.base = "https://www.youtube.com/watch?v="
        self.cookies = []
        self.checked = False
        self.cookie_dir = "anony/cookies"
        self.warned = False
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

    def get_cookies(self):
        if not self.checked:
            if os.path.exists(self.cookie_dir):
                for file in os.listdir(self.cookie_dir):
                    if file.endswith(".txt"):
                        self.cookies.append(f"{self.cookie_dir}/{file}")
            self.checked = True
        if not self.cookies:
            if not self.warned:
                self.warned = True
                logger.warning("Cookies are missing; downloads might fail.")
            return None
        return random.choice(self.cookies)

    async def save_cookies(self, urls: list[str]) -> None:
        logger.info("Saving cookies from urls...")
        async with aiohttp.ClientSession() as session:
            for url in urls:
                raw_name = url.split("/")[-1]
                # Sanitize: only alphanumeric and dash allowed in cookie name
                name = re.sub(r"[^\w\-]", "", raw_name)
                if not name:
                    logger.warning(f"Skipping invalid cookie URL: {url}")
                    continue
                link = "https://batbin.me/raw/" + name
                async with session.get(link) as resp:
                    resp.raise_for_status()
                    with open(f"{self.cookie_dir}/{name}.txt", "wb") as fw:
                        fw.write(await resp.read())
        logger.info(f"Cookies saved in {self.cookie_dir}.")

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

    def invalid(self, url: str) -> bool:
        return bool(re.match(self.iregex, url))

    async def search(self, query: str, m_id: int, video: bool = False) -> Track | None:
        try:
            _search = VideosSearch(query, limit=1)
            results = await _search.next()
            if results and results.get("result"):
                data = results["result"][0]
                return Track(
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
        except Exception as ex:
            logger.warning(f"YouTube search failed: {ex}")
        return None

    async def playlist(self, limit: int, user: str, url: str, video: bool) -> list[Track | None]:
        tracks = []
        try:
            plist = await Playlist.get(url)
            for data in plist.get("videos", [])[:limit]:
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
            logger.warning(f"YouTube playlist fetch failed: {ex}")
        return tracks

    @staticmethod
    def _sanitize_video_id(video_id: str) -> str | None:
        """Accept only valid YouTube video IDs (11 alphanumeric chars) or playlist IDs."""
        video_id = video_id.strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return video_id
        if re.fullmatch(r"PL[A-Za-z0-9_-]+", video_id):
            return video_id
        return None

    async def download(self, video_id: str, video: bool = False) -> str | None:
        # Sanitize video_id — this is the main injection prevention
        safe_id = self._sanitize_video_id(video_id)
        if not safe_id:
            logger.warning(f"Blocked suspicious video_id: {video_id!r}")
            return None
        video_id = safe_id

        # Try NexGen API first
        if self.api:
            if file_path := await self.api.download(video_id, video):
                return file_path

        # Fallback: yt-dlp
        url = self.base + video_id
        ext = "mp4" if video else "webm"
        filename = f"downloads/{video_id}.{ext}"

        if Path(filename).exists():
            return filename

        cookie = self.get_cookies()
        base_opts = {
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,
            "noplaylist": True,
            "geo_bypass": True,
            "no_warnings": True,
            "overwrites": False,
            "nocheckcertificate": True,
            "cookiefile": cookie,
        }

        if video:
            ydl_opts = {
                **base_opts,
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)",
                "merge_output_format": "mp4",
            }
        else:
            ydl_opts = {
                **base_opts,
                "format": "bestaudio[ext=webm][acodec=opus]",
            }

        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError):
                    return None
                except Exception as ex:
                    logger.warning("yt-dlp download failed: %s", ex)
                    return None
            return filename

        return await asyncio.to_thread(_download)
