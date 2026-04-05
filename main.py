import os
import asyncio
import logging
import shutil
import tempfile
from telethon import TelegramClient, events, Button
from dotenv import load_dotenv

load_dotenv()

# Local imports
from api import get_drama_detail, get_all_episodes
from downloader import download_all_episodes
from merge import merge_episodes
from uploader import upload_drama

# Configuration (Use environment variables or replace these directly)
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
AUTO_CHANNEL = int(os.environ.get("AUTO_CHANNEL", ADMIN_ID)) # Default post to admin
PROCESSED_FILE = "processed.json"

# Initialize state
def load_processed():
    if os.path.exists(PROCESSED_FILE):
        import json
        with open(PROCESSED_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_processed(data):
    import json
    with open(PROCESSED_FILE, "w") as f:
        json.dump(list(data), f)

processed_ids = load_processed()

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Bot State
class BotState:
    is_auto_running = True
    is_processing = False

# Initialize client
client = TelegramClient('dramabox_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

def get_panel_buttons():
    status_text = "🟢 RUNNING" if BotState.is_auto_running else "🔴 STOPPED"
    return [
        [Button.inline("▶️ Start Auto", b"start_auto"), Button.inline("⏹ Stop Auto", b"stop_auto")],
        [Button.inline(f"📊 Status: {status_text}", b"status")]
    ]

@client.on(events.NewMessage(pattern='/update'))
async def update_bot(event):
    if event.sender_id != ADMIN_ID:
        return
    import subprocess
    import sys
    
    status_msg = await event.reply("🔄 **Menarik pembaruan dari GitHub...**")
    try:
        # Run git pull
        result = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True)
        
        if "Already up to date" in result.stdout:
            await status_msg.edit("✅ **Bot sudah versi terbaru!** Tidak ada yang perlu diperbarui.")
            return

        await status_msg.edit(f"✅ **Update Berhasil!**\n\n```\n{result.stdout}\n```\nSedang memulai ulang layanan (Restarting via PM2)...")
        
        # Give a small delay to ensure the message is sent
        await asyncio.sleep(3)
        await client.disconnect()
        
        # Exit the process. PM2 will automatically restart it.
        sys.exit(0)
        
    except Exception as e:
        await status_msg.edit(f"❌ **Gagal melakukan update**: {e}")

@client.on(events.NewMessage(pattern='/panel'))
async def panel(event):
    if event.chat_id != ADMIN_ID:
        return
    await event.reply("🎛 **Dramabox Control Panel**", buttons=get_panel_buttons())

@client.on(events.CallbackQuery())
async def panel_callback(event):
    if event.sender_id != ADMIN_ID:
        return
        
    data = event.data
    
    try:
        if data == b"start_auto":
            BotState.is_auto_running = True
            await event.answer("Auto-mode dimulai!")
            await event.edit("🎛 **Panel Kontrol Drama**", buttons=get_panel_buttons())
        elif data == b"stop_auto":
            BotState.is_auto_running = False
            await event.answer("Auto-mode dihentikan!")
            await event.edit("🎛 **Panel Kontrol Drama**", buttons=get_panel_buttons())
        elif data == b"status":
            await event.answer(f"Status: {'Berjalan' if BotState.is_auto_running else 'Berhenti'}")
            await event.edit("🎛 **Panel Kontrol Drama**", buttons=get_panel_buttons())
    except Exception as e:
        if "message is not modified" in str(e).lower() or "Message string and reply markup" in str(e):
            pass # Ignore if button is already in that state
        else:
            logger.error(f"Callback error: {e}")

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("Selamat datang di Bot Downloader Drama! 🎉\n\nGunakan perintah `/download {ID_DRAMA}` untuk mulai.")

@client.on(events.NewMessage(pattern=r'/download (\d+)'))
async def on_download(event):
    chat_id = event.chat_id
    
    # Check admin
    if chat_id != ADMIN_ID:
        await event.reply("❌ Maaf, perintah ini hanya untuk admin.")
        return
        
    if BotState.is_processing:
        await event.reply("⚠️ Sedang memproses drama lain. Tunggu hingga selesai (Anti bentrok).")
        return
        
    book_id = event.pattern_match.group(1)
    
    # 1. Fetch data
    detail = await get_drama_detail(book_id)
    if not detail:
        await event.reply(f"❌ Gagal mendapatkan detail drama `{book_id}`.")
        return
        
    episodes = await get_all_episodes(book_id)
    if not episodes:
        await event.reply(f"❌ Drama `{book_id}` tidak memiliki episode.")
        return
    title = detail.get("title") or detail.get("bookName") or detail.get("name") or f"Drama_{book_id}"
    description = detail.get("intro") or detail.get("introduction") or detail.get("description") or "No description available."
    poster = detail.get("cover") or detail.get("coverWap") or detail.get("poster") or "" # URL for poster
    
    status_msg = await event.reply(f"🎬 Drama: **{title}**\n📽 Total Episode: {len(episodes)}\n\n⏳ Sedang mendownload dan memproses...")
    
    BotState.is_processing = True
    processed_ids.add(book_id)
    save_processed(processed_ids)
    
    await process_drama_full(book_id, chat_id, status_msg)
    BotState.is_processing = False

async def process_drama_full(book_id, chat_id, status_msg=None):
    """Refactored logic to be reusable for auto-mode."""
    detail = await get_drama_detail(book_id)
    episodes = await get_all_episodes(book_id)
    
    if not detail or not episodes:
        if status_msg: await status_msg.edit(f"❌ Detail atau Episode `{book_id}` tidak ditemukan.")
        return False

    title = detail.get("title") or detail.get("bookName") or detail.get("name") or f"Drama_{book_id}"
    description = detail.get("intro") or detail.get("introduction") or detail.get("description") or "Tidak ada sinopsis tersedia."
    poster = detail.get("cover") or detail.get("coverWap") or detail.get("poster") or ""
    
    # 2. Setup temp directory
    temp_dir = tempfile.mkdtemp(prefix=f"dramabox_{book_id}_")
    video_dir = os.path.join(temp_dir, "episodes")
    os.makedirs(video_dir, exist_ok=True)
    
    try:
        if status_msg: await status_msg.edit(f"🎬 Processing **{title}**...")
        
        # 3. Download
        success = await download_all_episodes(episodes, video_dir)
        if not success:
            if status_msg: await status_msg.edit("❌ Download Gagal.")
            return False

        # 4. Merge
        output_video_path = os.path.join(temp_dir, f"{title}.mp4")
        merge_success = merge_episodes(video_dir, output_video_path)
        if not merge_success:
            if status_msg: await status_msg.edit("❌ Merge Gagal.")
            return False

        # 5. Upload
        upload_success = await upload_drama(
            client, chat_id, 
            title, description, 
            poster, output_video_path
        )
        
        if upload_success:
            if status_msg: await status_msg.delete()
            return True
        else:
            if status_msg: await status_msg.edit("❌ Upload Gagal.")
            return False
            
    except Exception as e:
        logger.error(f"Error processing {book_id}: {e}")
        if status_msg: await status_msg.edit(f"❌ Error: {e}")
        return False
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

async def auto_mode_loop():
    """Loop to find and process new dramas automatically."""
    from api import get_latest_dramas
    global processed_ids
    
    logger.info("🚀 Full Auto-Mode Started.")
    
    # Run immediately on startup
    is_initial_run = True
    
    while True:
        if not BotState.is_auto_running:
            await asyncio.sleep(5)
            continue
            
        try:
            interval = 5 if is_initial_run else 15 # Check every 15 mins after first run
            logger.info(f"🔍 Scanning for new dramas (Next scan in {interval}m)...")
            
            # Step 1: Check Latest Discovery Endpoints (latest, foryou, homepage)
            dramas = await get_latest_dramas(pages=3 if is_initial_run else 1) or []
            
            # Step 2: If nothing new found, try POPULAR as fallback
            if not dramas:
                logger.info("🔎 No news found. Trying Popular Search fallback...")
                dramas = await get_latest_dramas(pages=1, types=["populersearch"]) or []
                
            new_found = 0
            
            for drama in dramas:
                if not BotState.is_auto_running:
                    break
                    
                # Handle different ID field names from API
                book_id = str(drama.get("bookId") or drama.get("id") or drama.get("bookid", ""))
                if not book_id:
                    continue
                    
                if book_id not in processed_ids:
                    # Segera tandai database sebagai diproses (Anti Duplicate)
                    processed_ids.add(book_id)
                    save_processed(processed_ids)
                    
                    new_found += 1
                    title = drama.get("title") or drama.get("bookName") or drama.get("name") or "Unknown"
                    logger.info(f"✨ Found new drama: {title} ({book_id}). Starting process...")
                    
                    # Process to target channel
                    final_msg = await client.send_message(ADMIN_ID, f"🆕 **Auto-System Mendeteksi Drama Baru!**\n🎬 `{title}`\n🆔 `{book_id}`\n⏳ Sedang diproses...")
                    
                    BotState.is_processing = True
                    success = await process_drama_full(book_id, AUTO_CHANNEL)
                    BotState.is_processing = False
                    
                    if success:
                        logger.info(f"✅ Finished {title}")
                        try:
                            # Cleanup initial notification
                            await final_msg.delete()
                            await client.send_message(ADMIN_ID, f"✅ **Selesai**: Drama `{title}` berhasil diposting!")
                        except: pass
                    else:
                        logger.error(f"❌ Failed to process {title}")
                        try:
                            await final_msg.delete()
                            await client.send_message(ADMIN_ID, f"⚠️ **Gagal memproses**: `{title}`\nSistem akan tetap berjalan.")
                        except: pass
                        continue
                    
                    # Prevent hitting API/Telegram rate limits too hard
                    await asyncio.sleep(10)
            
            if new_found == 0:
                logger.info("😴 No new dramas found in this scan.")
            
            is_initial_run = False
            
            # Wait for next interval but break early if auto_running is changed
            for _ in range(interval * 60):
                if not BotState.is_auto_running:
                    break
                await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"⚠️ Error in auto_mode_loop: {e}")
            await asyncio.sleep(60) # retry after 1 min

if __name__ == '__main__':
    logger.info("Initializing Dramabox Auto-Bot...")
    
    # Start auto loop and keep the client running
    client.loop.create_task(auto_mode_loop())
    
    logger.info("Bot is active and monitoring.")
    client.run_until_disconnected()
