# 🧾 LINE Budget Tracker

A LINE chatbot that scans Japanese receipt images using **Gemini 2.5 Flash** and replies with a structured spending summary — store name, category, date, total, payment method, and itemized breakdown.

---

## ✨ How It Works

1. User sends a receipt photo in LINE
2. The bot downloads the image via LINE Content API
3. **Gemini 2.5 Flash** parses the receipt into structured JSON
4. The bot replies with a formatted spending summary

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.10+ |
| Web framework | FastAPI + Uvicorn |
| LINE integration | LINE Messaging API |
| AI / OCR | Google Gemini 2.5 Flash |
| HTTP client | httpx (async) |
| Tunneling | ngrok |

---

## 📋 Prerequisites

- Python 3.10+
- A [LINE Developer account](https://developers.line.biz/) with a Messaging API channel
- A [Google AI Studio](https://aistudio.google.com/) API key (Gemini)
- [ngrok](https://ngrok.com/) installed

---

## 🚀 Setup & Installation

### 1. Clone the repository

```bash
git clone https://github.com/TemirlanSadykov/LINE-Budget-Tracker
cd LINE-Budget-Tracker
```

### 2. Create and activate a virtual environment

```bash
# Create venv
python -m venv venv

# Activate — macOS / Linux
source venv/bin/activate

# Activate — Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
CHANNEL_SECRET=your_line_channel_secret
GEMINI_API_KEY=your_gemini_api_key
DATABASE_URL=postgresql://user:password@host:port/dbname
```

| Variable | Where to find it |
|---|---|
| `CHANNEL_ACCESS_TOKEN` | LINE Developers Console → your channel → Messaging API → Channel access token |
| `CHANNEL_SECRET` | LINE Developers Console → your channel → Basic settings → Channel secret |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |
| `DATABASE_URL` | Railway → your project → Variables |

---

## ▶️ Running the App

### Start the server

```bash
python3 -m uvicorn app.main:app --port 3000
```

### Expose it publicly with ngrok

```bash
ngrok http 3000
```

Copy the `https://...ngrok-free.app` URL and set it as the **Webhook URL** in your LINE Developer Console:

```
https://<your-ngrok-subdomain>.ngrok-free.app/webhook
```

> Make sure **"Use webhook"** is enabled in the LINE console.

---

## 🧪 Testing the Receipt Parser

You can test the Gemini parser locally without LINE:

```bash
# parse only
python3 -m tests.receipt_scan static/images/Test.JPG

# parse + save to DB
python3 -m tests.receipt_scan static/images/Test.JPG --save
```

This runs the parser directly on a local image and prints the structured JSON + formatted reply to the terminal.

---

## 📂 Project Structure

```
LINE-Budget-Tracker/
├── app/
│   ├── __init__.py
│   ├── config.py                    # Environmental variables
│   ├── main.py                      # FastAPI entry point, lifespan
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py            # asyncpg pool management
│   │   ├── init_db.py               # table creation + seeding
│   │   └── migrations/
│   │       ├── init_tables.sql      # CREATE TABLE statements
│   │       └── seed.sql             # seed data (categories, payment methods)
│   ├── repositories/                # DB reads/writes, one file per entity
│   │   ├── __init__.py
│   │   ├── user_repo.py
│   │   ├── transaction_repo.py
│   │   ├── category_repo.py
│   │   └── payment_method_repo.py
│   ├── routers/                     # HTTP layer only
│   │   ├── __init__.py
│   │   └── webhook.py               # POST /webhook
│   └── services/                    # Business logic
│       ├── __init__.py
│       ├── line_service.py          # LINE API, event handling
│       └── receipt_service.py       # Gemini receipt parsing
├── static/
│       └── images/
│           └── Test.JPG             # Sample receipt for testing
├── tests/
│   └── test_receipt.py              # CLI tool for local parser testing
├── .env                             # API keys (not committed)
├── .env.example                     # ENV template
├── .gitignore
├── Procfile                         # Heroku/Railway process config
├── requirements.txt
└── README.md
```

---

## 🤖 Receipt Reply Format

When a receipt image is sent, the bot replies in this format:

```
🏪 セブン-イレブン
📂 コンビニ
📅 2025-04-28
💴 ¥1,250
💳 電子マネー

明細:
  • おにぎり 鮭  ¥160
  • お茶 500ml  ¥140
  • チョコレート  ¥320
  • 洗剤  ¥630
```

### Supported categories

`食費` · `交通費` · `日用品` · `カフェ` · `外食` · `ショッピング` · `その他`

### Supported payment methods

`現金` · `クレジットカード` · `電子マネー` · `QRコード` · `不明`

---

## ⚠️ Notes

- The webhook signature is verified using HMAC-SHA256 to ensure requests come from LINE.
- If the receipt cannot be parsed, the bot replies: `レシートの読み取りに失敗しました。`
- ngrok free tier generates a new URL each restart — update the LINE webhook URL each time.

---
