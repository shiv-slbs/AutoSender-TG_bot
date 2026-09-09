import asyncio
import csv
import json
import logging
import os
import random
import sys
import urllib.request
import urllib.error
import requests
from pyrogram import Client, errors
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Load env variables (if a local .env is present)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
POSTS_GSHEET_LINK = os.getenv("POSTS_GSHEET_LINK")
# 1. Exactly preserving negative sign per instructions
TARGET_CHAT_ID_RAW = os.getenv("TARGET_CHAT_ID")
try:
    if TARGET_CHAT_ID_RAW:
        TARGET_CHAT_ID = int(TARGET_CHAT_ID_RAW)
except ValueError:
    TARGET_CHAT_ID = TARGET_CHAT_ID_RAW

MIN_INTERVAL_MINUTES = int(os.getenv("MIN_INTERVAL_MINUTES", "15"))
MAX_INTERVAL_MINUTES = int(os.getenv("MAX_INTERVAL_MINUTES", "30"))

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Bot is running")

    # Silence default console logging for health check pings
    def log_message(self, format, *args):
        return

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Health check HTTP server successfully listening on 0.0.0.0:{port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Failed to bind dummy HTTP server on port {port}: {e}")

def validate_config():
    missing = []
    if not BOT_TOKEN: missing.append("BOT_TOKEN")
    if not API_ID: missing.append("API_ID")
    if not API_HASH: missing.append("API_HASH")
    if not TARGET_CHAT_ID: missing.append("TARGET_CHAT_ID")
    if not POSTS_GSHEET_LINK: missing.append("POSTS_GSHEET_LINK")
    
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)
        
    if MIN_INTERVAL_MINUTES > MAX_INTERVAL_MINUTES:
        logger.error("MIN_INTERVAL_MINUTES cannot be greater than MAX_INTERVAL_MINUTES.")
        sys.exit(1)

def fetch_posts_from_sheet(sheet_link, fallback_posts=None):
    if fallback_posts is None:
        fallback_posts = []
        
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(sheet_link, headers=headers, timeout=10)
        response.raise_for_status()
        
        reader = csv.DictReader(response.text.splitlines())
        posts = []
        for row in reader:
            post = {
                "id": row.get("id"),
                "text": row.get("text", ""),
                "media_url": row.get("media_url") or None,
                "parse_mode": row.get("parse_mode") or None,
                "button_text": row.get("button_text") or None,
                "button_url": row.get("button_url") or None
            }
            posts.append(post)
            
        if not posts:
            logger.warning("Google Sheet was empty or invalid, using previous posts.")
            return fallback_posts
            
        return posts
        
    except requests.RequestException as e:
        logger.warning(f"Network error fetching Google Sheet: {e}. Using previous posts.")
        return fallback_posts
    except Exception as e:
        logger.warning(f"Failed to parse Google Sheet CSV data: {e}. Using previous posts.")
        return fallback_posts

def dispatch_http_fallback(bot_token, chat_id, text, media_url, button_text, button_url, parse_mode_str):
    """Fallback using standard HTTP API if Pyrogram MTProto cache misses the Peer ID."""
    logger.info("Using HTTP API Fallback to bypass Pyrogram PeerIdInvalid cache miss.")
    method = "sendPhoto" if media_url else "sendMessage"
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    
    payload = {"chat_id": chat_id}
    
    if media_url:
        payload["photo"] = media_url
        if text:
            payload["caption"] = text
    else:
        payload["text"] = text
        
    if parse_mode_str:
        payload["parse_mode"] = parse_mode_str
        
    if button_text and button_url:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": button_text, "url": button_url}]]
        }
        
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode())
            if res.get("ok"):
                logger.info("HTTP Fallback dispatch completed successfully.")
            else:
                logger.error(f"HTTP Fallback dispatch failed: {res}")
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        logger.error(f"HTTP Fallback critical failure: {e}")
        if hasattr(e, 'read'):
            logger.error(e.read().decode())
        raise e

async def dispatch_post(client, post):
    text = post.get("text", "").replace("\\n", "\n")
    media_url = post.get("media_url")
    parse_mode_str = post.get("parse_mode", None)
    button_text = post.get("button_text")
    button_url = post.get("button_url")
    
    from pyrogram.enums import ParseMode
    parse_mode = None
    if parse_mode_str:
        pm_lower = parse_mode_str.lower()
        if pm_lower == "markdown": parse_mode = ParseMode.MARKDOWN
        elif pm_lower == "html": parse_mode = ParseMode.HTML
    
    reply_markup = None
    if button_text and button_url:
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, url=button_url)]])
        
    try:
        if media_url:
            await client.send_photo(
                chat_id=TARGET_CHAT_ID,
                photo=media_url,
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            await client.send_message(
                chat_id=TARGET_CHAT_ID,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    except errors.WebpageCurlFailed:
        logger.warning("Media URL unreachable by Telegram. Retrying as text-only message...")
        await client.send_message(
            chat_id=TARGET_CHAT_ID,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except (errors.PeerIdInvalid, ValueError) as e:
        if isinstance(e, ValueError) and "Peer id invalid" not in str(e):
            raise
        dispatch_http_fallback(BOT_TOKEN, TARGET_CHAT_ID, text, media_url, button_text, button_url, parse_mode_str)

async def main():
    logger.info(f"Loaded TARGET_CHAT_ID successfully. Value: {TARGET_CHAT_ID} Type: {type(TARGET_CHAT_ID)}")
    validate_config()
    
    app = Client(
        "bot_session",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN
    )
    
    await app.start()
    logger.info("Bot started successfully in MTProto mode.")
    
    post_deck = []
    
    try:
        while True:
            if not post_deck:
                logger.info("Deck empty or starting up. Fetching posts from Google Sheet...")
                # Fetch without fallback list so we can detect an empty payload natively
                fetched_posts = fetch_posts_from_sheet(POSTS_GSHEET_LINK, fallback_posts=None)
                if not fetched_posts:
                    logger.warning("Google Sheet data is empty or fetch failed. Retrying in 60s...")
                    await asyncio.sleep(60)
                    continue
                
                post_deck = fetched_posts.copy()
                random.shuffle(post_deck)
                logger.info(f"Deck shuffled and ready with {len(post_deck)} posts.")
                
            current_post = post_deck.pop()
            logger.info(f"Dispatching post ID: {current_post.get('id')}")
            
            try:
                await dispatch_post(app, current_post)
                logger.info(f"Successfully dispatched post ID: {current_post.get('id')}")
            except (errors.FloodWait, urllib.error.HTTPError) as e:
                # Basic handling - sleep and retry
                if isinstance(e, errors.FloodWait):
                    wait_time = e.value
                else:
                    wait_time = 30 # Default HTTP limit backoff
                logger.warning(f"Rate limited: sleeping for {wait_time} seconds.")
                await asyncio.sleep(wait_time)
                # Put the post back on top of the deck to be fetched next
                post_deck.append(current_post)
                continue
            except Exception as e:
                logger.error(f"Failed to dispatch post: {e}")
                
            sleep_s = random.randint(MIN_INTERVAL_MINUTES * 60, MAX_INTERVAL_MINUTES * 60)
            logger.info(f"Sleeping for {sleep_s} seconds ({sleep_s // 60} minutes)...")
            await asyncio.sleep(sleep_s)
            
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Bot shutting down...")
    finally:
        await app.stop()

if __name__ == "__main__":
    threading.Thread(target=start_dummy_server, daemon=True).start()
    asyncio.run(main())
