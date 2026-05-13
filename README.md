# 🧾 Kakei (家計) — LINE Budget Tracker

A bilingual (🇯🇵 / 🇬🇧) LINE chatbot that scans receipt images with **Gemini 2.5 Flash**, saves transactions to PostgreSQL, and shows monthly spending breakdowns inside LINE via a LIFF miniapp.

---

## ✨ How It Works

1. User follows the bot → bilingual welcome + language picker (Japanese / English)
2. User sends a receipt photo in LINE
3. Bot replies instantly with a "processing" message (Push API delivers the result)
4. **Gemini 2.5 Flash** parses the receipt → structured JSON (store, amount, category, date, payment method)
5. Bot sends a confirmation card — user confirms or edits each field (with Back buttons at every step)
6. User opens **マイプロフィール / My Profile** in the LINE menu → LIFF miniapp shows monthly stats by category

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.14 |
| Web framework | FastAPI + Uvicorn |
| Database | PostgreSQL (Railway) |
| Session state | Redis (Railway, 15-min TTL) |
| LINE integration | LINE Messaging API + LINE Login (LIFF) |
| AI / OCR | Google Gemini 2.5 Flash |
| HTTP client | httpx (async) |
| Tunneling (dev) | ngrok |

---

## 📋 Prerequisites

- Python 3.14
- [LINE Developer account](https://developers.line.biz/) with **two channels**:
  - **Messaging API channel** — for the chatbot
  - **LINE Login channel** — for the LIFF miniapp
- [Google AI Studio](https://aistudio.google.com/) API key (Gemini)
- PostgreSQL database (Railway recommended)
- Redis instance (Railway recommended)
- [ngrok](https://ngrok.com/) installed

---

## 🚀 Setup

### 1. Clone

```bash
git clone https://github.com/TemirlanSadykov/LINE-Budget-Tracker
cd LINE-Budget-Tracker
```

### 2. Virtual environment

```bash
python3.14 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment variables

Copy the template and fill in your values:

```bash
cp .env.example .env
```

`.env` contents:

```env
CHANNEL_ACCESS_TOKEN=your_messaging_api_channel_access_token
CHANNEL_SECRET=your_messaging_api_channel_secret
GEMINI_API_KEY=your_gemini_api_key
DATABASE_URL=postgresql://user:password@host:port/dbname
REDIS_URL=redis://default:password@host:port
LIFF_ID=your_liff_id
```

| Variable | Where to find it |
|---|---|
| `CHANNEL_ACCESS_TOKEN` | LINE Developers → Messaging API channel → Messaging API tab → Channel access token |
| `CHANNEL_SECRET` | LINE Developers → Messaging API channel → Basic settings → Channel secret |
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `DATABASE_URL` | Railway → your Postgres service → Variables → `DATABASE_URL` |
| `REDIS_URL` | Railway → your Redis service → Variables → `REDIS_URL` |
| `LIFF_ID` | See step 6 below |

### 5. Start the server

```bash
python3.14 -m uvicorn app.main:app --port 3000
```

The server auto-creates all DB tables and seeds categories/payment methods on first start.

### 6. Expose with ngrok

```bash
ngrok http 3000
```

Copy the `https://xxxx.ngrok-free.app` URL — you need it in two places:

**Webhook (Messaging API channel):**

```
https://xxxx.ngrok-free.app/webhook
```

Go to LINE Developers → Messaging API channel → Messaging API tab → Webhook URL. Enable **Use webhook**.

**LIFF endpoint (LINE Login channel):**

1. Go to LINE Developers → your **LINE Login channel** → LIFF tab
2. Create a LIFF app (size: `Full`, scope: `profile openid`)
3. Set Endpoint URL to:
   ```
   https://xxxx.ngrok-free.app/liff
   ```
4. Copy the generated **LIFF ID** (format: `1234567890-AbCdEfGh`) into your `.env` as `LIFF_ID`
5. Restart the server

> **Important:** ngrok free tier generates a new URL on every restart. Update **both** the webhook URL and the LIFF endpoint URL each time.

### 7. Link the LIFF to your bot's rich menu

In the LINE Official Account Manager, set the **マイプロフィール / My Profile** button to open:

```
https://liff.line.me/<your_liff_id>
```

---

## 🧪 Testing the Receipt Parser Locally

Test Gemini parsing without running LINE at all:

```bash
# Parse only — prints structured JSON
python3.14 -m tests.receipt_scan static/images/Test.JPG

# Parse + save to DB
python3.14 -m tests.receipt_scan static/images/Test.JPG --save
```

---

## 📂 Project Structure

```
LINE-Budget-Tracker/
├── app/
│   ├── config.py                    # Loads env vars
│   ├── constants.py                 # CATEGORIES and PAYMENT_METHODS (single source of truth, ja + en names)
│   ├── i18n.py                      # All user-facing strings in Japanese and English
│   ├── main.py                      # FastAPI entry point, lifespan hooks
│   ├── db/
│   │   ├── connection.py            # asyncpg pool
│   │   ├── init_db.py               # Table creation + seeding on startup
│   │   ├── redis.py                 # Redis client (session state)
│   │   └── migrations/
│   │       └── init_tables.sql      # CREATE TABLE statements
│   ├── repositories/
│   │   ├── user_repo.py             # create/deactivate user, get/set language preference
│   │   └── transaction_repo.py      # save, query, delete transactions
│   ├── routers/
│   │   ├── webhook.py               # POST /webhook (LINE events)
│   │   └── liff.py                  # GET /liff, GET /api/stats, DELETE /api/transaction/:id
│   ├── services/
│   │   ├── line_service.py          # Event handling, reply logic, state machine
│   │   ├── line_state_service.py    # Redis-backed conversation state (15 min TTL)
│   │   └── receipt_service.py       # Gemini receipt parsing
│   └── static/
│       └── liff/
│           └── index.html           # LIFF miniapp (monthly stats UI, bilingual)
├── static/
│   └── images/
│       └── Test.JPG                 # Sample receipt for local testing
├── tests/
│   └── receipt_scan.py              # CLI receipt parser test
├── .env.example                     # ENV template (copy to .env)
├── .gitignore
├── Procfile                         # Railway/Heroku: uvicorn app.main:app
├── requirements.txt                 # Pinned dependencies
└── README.md
```

---

## 🗺 LIFF Miniapp

Accessible via the **マイプロフィール / My Profile** button in the LINE chat menu.

- Displays in the user's chosen language (Japanese or English)
- Month navigation (‹ ›) — no future months allowed
- Total spend for the month
- Category breakdown with percentage bars
- Filter by payment method (chips: All / Cash / Card / e-Money / QR / Unknown)
- Sort by date or amount (asc / desc)
- Tap a category to expand individual transactions (date, payment method, memo)
- 🗑 Delete button per transaction

Authentication: LINE access token verified against `api.line.me/v2/profile` on every API call.

---

## 🤖 Bot Commands & Flow

| Trigger | Action |
|---|---|
| Follow event | Bilingual welcome + language picker (Japanese / English) |
| Language selected | Confirmation + usage guide sent |
| `言語変更` / `change language` (any case) | Language picker shown again |
| `使い方` / `help` (any case) | Usage instructions in user's language |
| `手動で入力` / `manual entry` / `manual` (any case) | Manual entry flow |
| Receipt image | Instant "processing" reply → Gemini parses → confirmation card |
| Confirm | Transaction saved to DB |
| Edit | Step-by-step: date → category → payment → amount → note (← Back at every step) |
| Confirm All (receipt) | Transaction saved directly from review card |
| Unfollow event | User deactivated in DB |

---

## ⚠️ Notes

- Webhook signature verified with HMAC-SHA256 — requests not from LINE are rejected with 400.
- Receipt image flow uses **two API calls**: reply token for instant "processing" acknowledgement, then Push API to deliver the parsed result.
- Conversation state stored in Redis with 15-minute TTL.
- Language preference (`ja` / `en`) stored in the `users` table and preserved across blocks/re-follows.
- DB tables and seed data are created automatically on server start — no manual migration needed.
- All category and payment method names are defined once in `constants.py` and translated at runtime — no duplication.
