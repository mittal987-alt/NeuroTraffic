"""
TrafficVision AI - YouTube Stream Helper
----------------------------------------
Resolves live or recorded YouTube stream URLs to direct video stream URLs
using yt-dlp.
"""

import yt_dlp


def get_direct_stream_url(youtube_url: str) -> str:
    """
    Extracts direct playable stream URL for a given YouTube link.
    Selects the best available mp4 format or fallback stream.
    """
    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        return info["url"]
