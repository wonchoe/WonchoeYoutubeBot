import os
import re
import sys
import time
import json
import fcntl
import logging
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

import yt_dlp

# ---------------------------------------------------
# LOGGING
# ---------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ytdl-bot")


# ---------------------------------------------------
# ENV
# ---------------------------------------------------
log.info("📄 Loading .env...")
load_dotenv(".env", override=True)


# ---------------------------------------------------
# ONE INSTANCE LOCK
# ---------------------------------------------------
def acquire_lock_or_exit():
    try:
        lock_file = "/tmp/ytdlbot.lock"
        global lock_fp
        lock_fp = open(lock_file, 'w')
        fcntl.lockf(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        log.info("🔒 Lock acquired")
    except IOError:
        log.error("🚫 Another instance already running!")
        sys.exit(1)


acquire_lock_or_exit()


# ---------------------------------------------------
# GLOBAL STORAGE
# ---------------------------------------------------
# Тимчасове сховище для того, щоб опрацювати callback після отримання URL
LINK_STORAGE = {}  # chat_id → url


# ---------------------------------------------------
# CALLBACK KEYS
# ---------------------------------------------------
AUDIO = "audio"
VIDEO = "video"
VIDEO_QUALITY = "video_quality"


# ---------------------------------------------------
# HELPERS: PROGRESS BAR
# ---------------------------------------------------
def make_progress_bar(percent: float) -> str:
    filled = int(percent / 5)  # 20 chars total
    bar = "█" * filled + "░" * (20 - filled)
    return f"[{bar}] {percent:.1f}%"


# ---------------------------------------------------
# EXTRACT AVAILABLE VIDEO FORMATS
# ---------------------------------------------------
async def extract_formats(url: str):
    log.info("🔎 Extracting available formats...")

    ydl_opts = {
        "quiet": True,
        "nocheckcertificate": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = info.get("formats", [])

    # Забираємо лише ті, що мають height (роздільну здатність)
    out = {}
    for f in formats:
        height = f.get("height")
        ext = f.get("ext")
        if height and ext in ["mp4", "webm"]:
            out[height] = f["format_id"]

    # Сортуємо від найвищої якості до найнижчої
    sorted_out = dict(sorted(out.items(), reverse=True))
    return sorted_out


# ---------------------------------------------------
# DOWNLOAD WITH PROGRESS + SEND
# ---------------------------------------------------
async def download_and_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    mode: str,
    quality_format_id: str | None = None
):
    chat_id = update.effective_chat.id

    status_msg = await context.bot.send_message(
        chat_id, "⏳ Preparing download..."
    )

    download_dir = Path(os.environ.get("DOWNLOAD_DIR", "downloads"))
    download_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------
    # ПРОГРЕС ХУК
    # ---------------------------
    last_update = 0

    async def progress_hook(d):
        nonlocal last_update

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)

            if total > 0:
                percent = downloaded / total * 100
                if time.time() - last_update > 0.5:
                    last_update = time.time()
                    bar = make_progress_bar(percent)
                    try:
                        await status_msg.edit_text(
                            f"⬇️ Downloading...\n{bar}"
                        )
                    except:
                        pass
            else:
                if time.time() - last_update > 0.5:
                    last_update = time.time()
                    mb = downloaded / 1024 / 1024
                    try:
                        await status_msg.edit_text(
                            f"⬇️ Downloading...\n{mb:.1f} MB"
                        )
                    except:
                        pass

        elif d["status"] == "finished":
            try:
                await status_msg.edit_text("🔄 Converting / Finalizing...")
            except:
                pass

    # ---------------------------
    # DOWNLOAD OPTIONS
    # ---------------------------
    if mode == AUDIO:
        ydl_opts = {
            "format": "bestaudio/best",
            "cookiefile": "/tmp/cookies.txt",
            "outtmpl": str(download_dir / "%(title)s.%(ext)s"),
            "quiet": True,
            "nocheckcertificate": True,
            "progress_hooks": [lambda d: asyncio.create_task(progress_hook(d))],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }],
        }
    else:  # VIDEO
        if quality_format_id:
            fmt = f"{quality_format_id}+bestaudio/best"
        else:
            fmt = "bestvideo+bestaudio"

        ydl_opts = {
            "format": fmt,
            "cookiefile": "/tmp/cookies.txt",
            "outtmpl": str(download_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "quiet": True,
            "nocheckcertificate": True,
            "progress_hooks": [lambda d: asyncio.create_task(progress_hook(d))],
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        filepath = Path(ydl.prepare_filename(info))

        # Якщо це аудіо — замінимо суфікс на .mp3
        if mode == AUDIO:
            filepath = filepath.with_suffix(".mp3")

        await status_msg.edit_text("📤 Uploading to Telegram...")

        # надсилання файлу
        with filepath.open("rb") as f:
            await context.bot.send_document(
                chat_id,
                document=InputFile(f, filename=filepath.name),
                caption="Готово ✔"
            )

        await status_msg.edit_text("✅ Done!")

    except Exception as e:
        log.error(f"❌ Error: {e}")
        await status_msg.edit_text(f"⚠️ Error: {e}")


# ---------------------------------------------------
# MESSAGE HANDLER
# ---------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    text = msg.text.strip()

    youtube_regex = re.compile(r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[^\s]+")
    match = youtube_regex.search(text)

    if not match:
        await msg.reply_text("Будь ласка, надішліть коректне посилання на YouTube.")
        return

    url = match.group(0)
    LINK_STORAGE[update.effective_chat.id] = url

    keyboard = [
        [InlineKeyboardButton("🎧 Audio (MP3)", callback_data=AUDIO)],
        [InlineKeyboardButton("🎬 Video (MP4)", callback_data=VIDEO)],
    ]

    await msg.reply_text(
        "Що хочете завантажити?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ---------------------------------------------------
# CALLBACK HANDLER
# ---------------------------------------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    url = LINK_STORAGE.get(chat_id)

    if not url:
        await query.edit_message_text("⚠️ Посилання не знайдене. Надішліть його ще раз.")
        return

    data = query.data

    # ----------------------------- AUDIO -----------------------------
    if data == AUDIO:
        await query.edit_message_text("🎧 Завантаження аудіо...")
        await download_and_send(update, context, url, AUDIO)
        return

    # ----------------------------- VIDEO -----------------------------
    if data == VIDEO:
        await query.edit_message_text("🔎 Збираємо доступні формати...")
        formats = await extract_formats(url)

        if not formats:
            await query.edit_message_text("⚠️ Не вдалося отримати список якостей.")
            return

        keyboard = [
            [
                InlineKeyboardButton(
                    f"{height}p",
                    callback_data=f"{VIDEO_QUALITY}:{height}"
                )
            ]
            for height in formats.keys()
        ]

        await query.edit_message_text(
            "Оберіть якість відео:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # -------------------- SELECT VIDEO QUALITY -----------------------
    if data.startswith(f"{VIDEO_QUALITY}:"):
        _, height_str = data.split(":")
        height = int(height_str)

        formats = await extract_formats(url)
        format_id = formats.get(height)

        await query.edit_message_text(f"🎬 Завантаження {height}p...")
        await download_and_send(update, context, url, VIDEO, format_id)


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------
def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        log.critical("❗ TELEGRAM_BOT_TOKEN not set!")
        raise RuntimeError("Missing token")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    log.info("🤖 Bot started (polling)...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
