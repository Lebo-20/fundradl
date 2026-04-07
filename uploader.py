import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo
import logging

logger = logging.getLogger(__name__)

async def upload_progress(current, total, event, msg_text="Uploading..."):
    """Callback function for upload progress."""
    percentage = (current / total) * 100
    try:
        if int(percentage) % 10 == 0:
            await event.edit(f"{msg_text} {percentage:.1f}%")
    except:
        pass

async def upload_drama(client: TelegramClient, chat_id: int, 
                       title: str, description: str, 
                       poster_url: str, video_path: str):
    """
    Uploads the drama information and merged video to Telegram.
    Sequence:
    1. Send progress message.
    2. Upload video.
    3. Send Poster + Description (Clean).
    4. Send Video (Clean).
    5. Cleanup status message.
    """
    import subprocess
    import tempfile
    
    status_msg = None
    try:
        # Prepare caption
        caption = f"🎬 **{title}**\n\n📝 **Sinopsis:**\n{description[:900]}..."
        
        status_msg = await client.send_message(chat_id, f"📡 **[{title}]**\n⚙️ Menyiapkan file & ekstraksi metadata...")
        
        # 1. Extract Duration & Dimensions
        duration = 0
        width = 0
        height = 0
        try:
            ffprobe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
            output = subprocess.check_output(ffprobe_cmd, text=True).strip().split('\n')
            if len(output) >= 3:
                width = int(output[0])
                height = int(output[1])
                duration = int(float(output[2]))
            elif len(output) == 1:
                duration = int(float(output[0]))
        except: pass

        # 2. Extract Thumbnail
        thumb_path = os.path.join(tempfile.gettempdir(), f"thumb_{os.path.basename(video_path)}.jpg")
        try:
            subprocess.run(["ffmpeg", "-y", "-i", video_path, "-ss", "00:00:01.000", "-vframes", "1", thumb_path], capture_output=True)
            if not os.path.exists(thumb_path): thumb_path = None
        except: thumb_path = None

        # 3. Upload Video First (Silently if possible)
        await status_msg.edit(f"📤 **[{title}]**\nSedang mengupload video ke Telegram...")
        
        video_attributes = [
            DocumentAttributeVideo(
                duration=duration,
                w=width,
                h=height,
                supports_streaming=True
            )
        ]
        
        # We send the final messages in a clean sequence
        logger.info(f"Uploading final video for {title}")
        
        # Send Poster + Details first (Permanent)
        if poster_url and str(poster_url).strip():
            await client.send_file(
                chat_id,
                poster_url,
                caption=caption,
                force_document=False
            )
        else:
            # Fallback if poster is empty
            await client.send_message(
                chat_id,
                caption
            )
        
        # Send Video (Permanent)
        await client.send_file(
            chat_id,
            video_path,
            caption=f"🎥 **Full Episode: {title}**",
            force_document=False,
            thumb=thumb_path,
            attributes=video_attributes,
            progress_callback=lambda c, t: upload_progress(c, t, status_msg, f"📤 Uploading Video:"),
            supports_streaming=True
        )
        
        # Cleanup
        if status_msg: await status_msg.delete()
        if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
            
        logger.info(f"Successfully uploaded {title} to Telegram")
        return True

    except Exception as e:
        logger.error(f"Failed to upload to Telegram: {e}")
        if status_msg:
            try: await status_msg.edit(f"❌ **Upload Gagal**: {e}")
            except: pass
        return False
