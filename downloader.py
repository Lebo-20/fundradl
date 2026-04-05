import os
import asyncio
import httpx
import logging
import re

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


async def download_all_episodes(episodes, download_dir: str, semaphore_count: int = 5):
    """
    Download semua episode dari FunDrama API secara paralel dengan retry.
    """
    os.makedirs(download_dir, exist_ok=True)
    semaphore = asyncio.Semaphore(semaphore_count)

    async def limited_download(ep, retries=3):
        async with semaphore:
            ep_num = str(ep.get('episode', 'unk')).zfill(3)
            video_filename = f"episode_{ep_num}.mp4"
            subtitle_filename = f"episode_{ep_num}.vtt"
            video_path = os.path.join(download_dir, video_filename)
            subtitle_path = os.path.join(download_dir, subtitle_filename)

            # Skip jika sudah ada dan valid
            if os.path.exists(video_path) and os.path.getsize(video_path) > 1024:
                logger.info(f"⏭ Skip {video_filename} (sudah ada)")
                return True

            for attempt in range(retries):
                try:
                    drama_id = ep.get("dramaId") or ep.get("id")
                    ep_number = ep.get("ep") or ep.get("episode")

                    # Prioritas 1: play_url sudah ada langsung di data episode (API baru)
                    m3u8_url = ep.get("play_url") or ""
                    subtitle_url = ep.get("subtitle") or ""
                    cookies = {}

                    # Prioritas 2: Fallback ke /unlock jika play_url kosong
                    if not m3u8_url:
                        from api import get_stream_url
                        stream_data = await get_stream_url(drama_id, ep_number)
                        if not stream_data or not stream_data.get("m3u8"):
                            logger.warning(f"⚠️ Attempt {attempt+1}: URL stream kosong ep{ep_num}")
                            await asyncio.sleep(5 * (attempt + 1))
                            continue
                        m3u8_url = stream_data["m3u8"]
                        subtitle_url = stream_data.get("subtitle") or ""
                        cookies = stream_data.get("cookies") or {}

                    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()]) if cookies else ""

                    # Download video via FFmpeg
                    ffmpeg_cmd = [
                        "ffmpeg", "-y",
                        "-headers", f"Cookie: {cookie_str}\r\nUser-Agent: {HEADERS['User-Agent']}\r\n",
                        "-i", m3u8_url,
                        "-c", "copy", "-bsf:a", "aac_adtstoasc",
                        video_path
                    ]

                    proc = await asyncio.create_subprocess_exec(
                        *ffmpeg_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    _, stderr = await proc.communicate()

                    if os.path.exists(video_path) and os.path.getsize(video_path) > 1024:
                        # Download subtitle jika ada
                        if subtitle_url:
                            try:
                                async with httpx.AsyncClient(timeout=20, headers=HEADERS) as sclient:
                                    s_res = await sclient.get(subtitle_url, cookies=cookies)
                                    if s_res.status_code == 200:
                                        with open(subtitle_path, "wb") as sf:
                                            sf.write(s_res.content)
                                        logger.info(f"📝 Subtitle: {subtitle_filename}")
                            except:
                                pass

                        logger.info(f"✅ Berhasil: {video_filename} (Attempt {attempt+1})")
                        return True
                    else:
                        logger.warning(f"⚠️ Attempt {attempt+1} gagal: {video_filename}")
                        if stderr:
                            logger.debug(f"FFmpeg stderr: {stderr.decode()[-300:]}")
                        if os.path.exists(video_path):
                            os.remove(video_path)

                except Exception as e:
                    logger.error(f"❌ Attempt {attempt+1} Error ep{ep_num}: {e}")

                await asyncio.sleep(3 * (attempt + 1))

            logger.error(f"❌ Gagal setelah {retries} attempt: {video_filename}")
            return False

    results = await asyncio.gather(*(limited_download(ep) for ep in episodes))
    return all(results)
