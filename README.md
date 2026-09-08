# Telegram Auto-Broadcaster Bot

A robust, asynchronous Telegram broadcasting Python bot built with [Pyrogram](https://docs.pyrogram.org/). This bot dynamically fetches content from a published Google Sheet and posts it automatically to a designated Telegram channel or group at randomized intervals.

## 🚀 Features
- **Dynamic Content Fetching**: Directly pulls data identically mapped from a published Google Sheet (CSV format). If you edit your sheet, the bot detects changes securely on the next cycle—no restart required.
- **Shuffle-Bag Queue (Deck of Cards)**: Creates a randomized "deck" of scheduled posts. It shuffles the content, loops sequentially through the items, and efficiently recalculates and fetches the sheet only once the deck is completely empty. 
- **Graceful Error Handling**: 
  - Intercepts API `FloodWait` (Rate limit) errors and automatically sleeps the penalty time before pushing the failed post back onto the top of the deck to securely retry.
  - Defaults to native Pyrogram `send_message` and `send_photo` MTProto API calls, combined with a seamless HTTP API fallback algorithm in case of new-channel `PeerIdInvalid` cache misses on cold boots.
  - Safely buffers network timeouts or temporary API failures by waiting and gracefully retrying without ever crashing the worker.
- **Rich Media & Formatting**: Fully supports inline reply-buttons, dispatching remote media URLs, and parses raw text natively using either Markdown or HTML.

## 🛠️ Prerequisites
- Python 3.8+
- A valid Telegram [Bot Token](https://core.telegram.org/bots#botfather)
- Your Telegram `API_ID` & `API_HASH` from [my.telegram.org](https://my.telegram.org)
- A Google Sheet URL exported seamlessly as a CSV. 

## ⚙️ Configuration & Environment Setup
Duplicate `.env.example` to `.env` and fill in your variables:

```env
BOT_TOKEN=your_bot_token_here
API_ID=your_api_id
API_HASH=your_api_hash
TARGET_CHAT_ID=-100xxxxxxx     # Use the exact negative numerical ID for channels
MIN_INTERVAL_MINUTES=15        # Minimum randomization constraint (minutes) 
MAX_INTERVAL_MINUTES=30        # Maximum randomization constraint (minutes)
POSTS_GSHEET_LINK=https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/export?format=csv
```

### Google Sheet Requirements
Ensure your Google Sheet utilizes these exact case-sensitive header columns in row 1:
- `id`: A unique identifier for the specific post
- `text`: Body caption (or standard message text if no media is sent)
- `media_url` *(optional)*: Direct link to an image/photo
- `parse_mode` *(optional)*: Accepts `html` or `markdown`
- `button_text` *(optional)*: Text label for the interactive Inline Button
- `button_url` *(optional)*: Hyperlink route for the Inline Button

## 🏃 Running Locally
1. Clone the repository and navigate to the root directory:
   ```bash
   git clone <your-repo-link>
   cd "TG Bot"
   ```
2. Install the rigid package requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the application:
   ```bash
   python main.py
   ```

## ☁️ Production Deployment (e.g., Render)
This project is configured right out of the box for standard background-worker deployment endpoints. 
- Push the compiled repository securely to GitHub.
- Provision a new **Background Worker** (Render) or equivalent Dyno service.
- Bind the start command explicitly to `python main.py`.
- Map your environment keys natively within your deployment dashboard. 
- *(Note: Your `.gitignore` natively blocks local configurations, guaranteeing `.session` files safely spawn implicitly on bot deployment without breaking standard Git pipelines).*
