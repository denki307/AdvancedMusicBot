
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import AudioPiped
from pytgcalls.types.input_stream.quality import HighQualityAudio
from pymongo import MongoClient
import yt_dlp

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
SESSION_STRING = os.getenv("SESSION_STRING")
MONGO_URL = os.getenv("MONGO_URL")
START_PIC = os.getenv("START_PIC")

app = Client("MusicBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
assistant = Client("Assistant", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
call = PyTgCalls(assistant)

mongo = MongoClient(MONGO_URL)
db = mongo.musicbot
queue_db = db.queue

def add_to_queue(chat_id, data):
    queue_db.insert_one({"chat_id": chat_id, "data": data})

def get_queue(chat_id):
    return list(queue_db.find({"chat_id": chat_id}))

def clear_queue(chat_id):
    queue_db.delete_many({"chat_id": chat_id})

def pop_next(chat_id):
    song = queue_db.find_one({"chat_id": chat_id})
    if song:
        queue_db.delete_one({"_id": song["_id"]})
        return song["data"]
    return None

async def download_song(query):
    ydl_opts = {"format": "bestaudio", "quiet": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=True)["entries"][0]
        file = ydl.prepare_filename(info)
        return file, info["title"], info["thumbnail"]

@app.on_message(filters.command("start"))
async def start(_, message):
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me To Group",
         url=f"https://t.me/{(await app.get_me()).username}?startgroup=true")],
        [InlineKeyboardButton("🎵 Commands", callback_data="help")]
    ])
    await message.reply_photo(
        photo=START_PIC,
        caption="🎶 **Advanced Voice Chat Music Bot**\n\nUse me in your group voice chat!",
        reply_markup=buttons
    )

@app.on_callback_query(filters.regex("help"))
async def help_menu(_, query):
    await query.message.edit_caption(
        caption="📜 **Commands**\n\n/play song\n/skip\n/pause\n/resume\n/stop",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
    )

@app.on_callback_query(filters.regex("back"))
async def back_menu(_, query):
    await start(_, query.message)

@app.on_message(filters.command("play") & filters.group)
async def play(_, message):
    chat_id = message.chat.id
    query = message.text.split(None, 1)[1]

    msg = await message.reply("🔍 Downloading...")
    file, title, thumb = await download_song(query)

    if not await call.get_call(chat_id):
        await call.join_group_call(chat_id, AudioPiped(file, HighQualityAudio()))
    else:
        add_to_queue(chat_id, file)
        return await msg.edit("➕ Added to Queue")

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏸ Pause", callback_data="pause"),
            InlineKeyboardButton("⏭ Skip", callback_data="skip")
        ],
        [InlineKeyboardButton("⏹ Stop", callback_data="stop")]
    ])

    await msg.delete()
    await message.reply_photo(
        photo=thumb,
        caption=f"🎶 **Now Playing:** {title}",
        reply_markup=buttons
    )

@app.on_callback_query(filters.regex("pause"))
async def pause(_, query):
    await call.pause_stream(query.message.chat.id)
    await query.answer("Paused")

@app.on_callback_query(filters.regex("skip"))
async def skip(_, query):
    chat_id = query.message.chat.id
    next_song = pop_next(chat_id)
    if next_song:
        await call.change_stream(chat_id, AudioPiped(next_song))
        await query.answer("Skipped")
    else:
        await call.leave_group_call(chat_id)
        await query.answer("Queue Empty")

@app.on_callback_query(filters.regex("stop"))
async def stop(_, query):
    chat_id = query.message.chat.id
    clear_queue(chat_id)
    await call.leave_group_call(chat_id)
    await query.answer("Stopped")

assistant.start()
call.start()
app.run()
