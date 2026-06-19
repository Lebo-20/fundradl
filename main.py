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

# Initialize client placeholder
client = None

async def get_client():
    global client
    if client is None:
        client = TelegramClient('fundrama_bot', API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
    return client

def get_panel_buttons():
    status_text = "🟢 RUNNING" if BotState.is_auto_running else "🔴 STOPPED"
    return [
        [Button.inline("▶️ Start Auto", b"start_auto"), Button.inline("⏹ Stop Auto", b"stop_auto")],
        [Button.inline(f"📊 Status: {status_text}", b"status")]
    ]

@events.register(events.NewMessage(pattern='/update'))
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

@events.register(events.NewMessage(pattern='/panel'))
async def panel(event):
    if event.chat_id != ADMIN_ID:
        return
    await event.reply("🎛 **FunDrama Control Panel**", buttons=get_panel_buttons())

@events.register(events.CallbackQuery())
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

@events.register(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("Selamat datang di Bot Downloader Drama! 🎉\n\nGunakan perintah `/download {ID_DRAMA}` untuk mulai.")

@events.register(events.NewMessage(pattern='/batch'))
async def on_batch(event):
    if event.chat_id != ADMIN_ID:
        return
        
    if BotState.is_processing:
        await event.reply("⚠️ Bot sedang sibuk memproses drama lain.")
        return

    if not os.path.exists("new_found.json"):
        await event.reply("❌ File `new_found.json` tidak ditemukan. Jalankan ekstraksi ID dulu.")
        return

    with open("new_found.json", "r", encoding="utf-8") as f:
        import json
        dramas = json.load(f)

    if not dramas:
        await event.reply("✅ Tidak ada drama baru untuk diproses.")
        return

    # Filter out already processed
    to_process = [d for d in dramas if d["id"] not in processed_ids]
    if not to_process:
        await event.reply("✅ Semua drama di list sudah pernah diproses.")
        return

    status_msg = await event.reply(f"🚀 **Memulai Batch Processing untuk {len(to_process)} drama...**")
    BotState.is_processing = True
    
    success_count = 0
    fail_count = 0
    
    for i, drama in enumerate(to_process):
        drama_id = drama["id"]
        title = drama["title"]
        
        # Double check title if it's just an ID
        if title.isdigit():
            det = await get_drama_detail(drama_id)
            if det and det.get("title"):
                title = det["title"]
            
        await status_msg.edit(f"🔄 **Batch ({i+1}/{len(dramas)})**\n🎬 Drama: `{title}`\n⏳ Sedang diproses...")
        
        success = await process_drama_full(drama_id, AUTO_CHANNEL)
        if success:
            processed_ids.add(drama_id)
            save_processed(processed_ids)
            success_count += 1
        else:
            fail_count += 1
            
        # Prevent rate limits
        await asyncio.sleep(5)
        
    BotState.is_processing = False
    await status_msg.edit(f"🏁 **Batch Processing Selesai!**\n✅ Berhasil: {success_count}\n❌ Gagal: {fail_count}")

@events.register(events.NewMessage(pattern=r'/download (\d+)'))
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
    poster = detail.get("cover") or detail.get("coverWap") or detail.get("poster") or "" 
    
    # If title is still just the ID, it's not helpful
    if title.isdigit() or title == f"Drama_{book_id}":
        title = f"Drama {book_id}"

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
    temp_dir = tempfile.mkdtemp(prefix=f"fundrama_{book_id}_")
    video_dir = os.path.join(temp_dir, "episodes")
    os.makedirs(video_dir, exist_ok=True)
    
    try:
        if status_msg: await status_msg.edit(f"🎬 Processing **{title}**...")
        
        # 3. Download
        success = await download_all_episodes(episodes, video_dir)
        if not success:
            if status_msg: await status_msg.edit("❌ Download Gagal. Beberapa episode tidak bisa diambil.")
            return False

        # 4. Merge
        if status_msg: await status_msg.edit(f"🎬 **{title}**\n📥 Download Selesai!\n🔄 Sedang menggabungkan (Merging) episode...")
        
        output_video_path = os.path.join(temp_dir, f"{title}.mp4")
        merge_success = merge_episodes(video_dir, output_video_path)
        if not merge_success:
            if status_msg: await status_msg.edit("❌ Merge Gagal.")
            return False

        # 5. Upload
        current_client = await get_client()
        upload_success = await upload_drama(
            current_client, chat_id, 
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
            import time
            # Give OS a moment to release file handles (especially on Windows)
            await asyncio.sleep(2)
            for _ in range(3):
                try:
                    shutil.rmtree(temp_dir)
                    break
                except Exception as e:
                    logger.warning(f"Retrying cleanup for {temp_dir}: {e}")
                    await asyncio.sleep(2)

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
            interval = 5 if is_initial_run else 120 # Check every 15 mins after first run
            logger.info(f"🔍 Scanning for new dramas (Next scan in {interval}m)...")
            
            # Step 1: Check multiple segments for discovery
            # We scan 'dramas' (latest), 'discovery' (homepage), and 'popular'
            search_types = ["dramas", "discovery", "popular"]
            dramas = await get_latest_dramas(pages=2 if is_initial_run else 1, types=search_types) or []
            
            # Step 2: Fallback if still nothing found
            if not dramas:
                logger.info("🔎 No news found. Trying Search Hot fallback...")
                dramas = await get_latest_dramas(pages=1, types=["search_hot"]) or []
                
            new_found = 0
            
            for drama in dramas:
                if not BotState.is_auto_running:
                    break
                    
                # Handle different ID field names from API
                book_id = str(drama.get("bookId") or drama.get("id") or drama.get("bookid", ""))
                if not book_id:
                    continue
                    
                if book_id not in processed_ids:
                    # Check if bot is busy before starting auto-process
                    while BotState.is_processing:
                        await asyncio.sleep(10)
                        if not BotState.is_auto_running: break
                    
                    if not BotState.is_auto_running: break

                    # Segera tandai database sebagai diproses (Anti Duplicate)
                    processed_ids.add(book_id)
                    save_processed(processed_ids)
                    
                    new_found += 1
                    title = drama.get("title") or drama.get("bookName") or drama.get("name") or str(book_id)
                    
                    # Force fetch detail to get real title if current is just digits
                    # This title will be LOCKED for the entire process duration
                    if title.isdigit() or title == str(book_id):
                        logger.info(f"🔍 Fetching real title for ID: {book_id}...")
                        detail = await get_drama_detail(book_id)
                        if detail and detail.get("title") and not detail.get("title").isdigit():
                            title = detail["title"]
                    
                    logger.info(f"✨ Found new drama: {title} ({book_id}). Starting process...")
                    
                    # Process to target channel
                    final_msg = await client.send_message(ADMIN_ID, f"🆕 **Auto-System Mendeteksi Drama Baru!**\n🎬 `{title}`\n🆔 `{book_id}`\n⏳ Sedang diproses...")
                    
                    BotState.is_processing = True
                    # The process_drama_full must NOT change the title
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

async def main():
    logger.info("Initializing FunDrama Auto-Bot...")
    
    current_client = await get_client()
    
    # Add handlers
    current_client.add_event_handler(update_bot)
    current_client.add_event_handler(panel)
    current_client.add_event_handler(panel_callback)
    current_client.add_event_handler(start)
    current_client.add_event_handler(on_batch)
    current_client.add_event_handler(on_download)
    
    # Start auto loop and keep the client running
    asyncio.create_task(auto_mode_loop())
    
    logger.info("Bot is active and monitoring.")
    await current_client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
