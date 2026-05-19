# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic


import os
import re
import asyncio
import aiohttp
from pathlib import Path

from py_yt import VideosSearch, Playlist

from anony import logger, config
from anony.helpers import Track, utils


class NexGenApi:
    def __init__(self, api_url: str, video_api_url: str, api_key: str, retries: int = 10, timeout: int = 40):
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

    async def save_file(self, vid_id: str, url: str, video: bool = False) -> str | None:
        try:
            async with self.session.get(url) as resp:
                if resp.status != 200:
                    return None

                cd = resp.headers.get("Content-Disposition")
                if cd and (match := re.search(r'filename="?(.+?)"?$', cd)):
                    file_name = match.group(1)
                else:
                    file_name = vid_id + (".mp4" if video else ".mp3")

                fname = f"downloads/{file_name}"
                with open(fname, "wb") as f:
                    async for chunk in resp.content.iter_chunked(self.chunk_limit):
                        if chunk: f.write(chunk)

                if video: self.v_cache[vid_id] = fname
                else: self.dl_cache[vid_id] = fname

                return fname
        except Exception:
            pass
        return None

    async def download(self, vid_id: str, video: bool = False) -> str | None:
        if video and vid_id in self.v_cache:
            return self.v_cache[vid_id]
        elif not video and vid_id in self.dl_cache:
            return self.dl_cache[vid_id]

        endp = f"{self.video_api_url}/video/{vid_id}?api={self.api_key}" if video else f"{self.api_url}/song/{vid_id}?api={self.api_key}"

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
        self.regex = re.compile(
            r"(https?://)?(www\.|m\.|music\.)?"
            r"(youtube\.com/(watch\?v=|shorts/|playlist\?list=)|youtu\.be/)"
            r"([A-Za-z0-9_-]{11}|PL[A-Za-z0-9_-]+)([&?][^\s]*)?"
        )
        if config.API_URL and config.VIDEO_API_URL and config.API_KEY:
            self.api = NexGenApi(config.API_URL, config.VIDEO_API_URL, config.API_KEY)

    def valid(self, url: str) -> bool:
        return bool(re.match(self.regex, url))

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

    async def download(self, video_id: str, video: bool = False) -> str | None:
        if self.api:
            if file_path := await self.api.download(video_id, video):
                return file_path
        logger.warning(f"NexGen API failed or not configured for {video_id}")
        return None
