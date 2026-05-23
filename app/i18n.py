"""
All user-facing bot strings in Japanese and English.
Usage: t("key", lang)  where lang is "ja" or "en"
"""

_S: dict[str, dict[str, str]] = {
    "ja": {
        # ── Language selection ──────────────────────────────
        "lang_select":          "🌏 言語を選んでください\n\nPlease choose your language:",
        "lang_btn_ja":          "🇯🇵 日本語",
        "lang_btn_en":          "🇬🇧 English",
        "lang_saved_ja":        "🇯🇵 日本語に設定しました！",

        # ── Photo processing ────────────────────────────────
        "processing":           "📷 レシートを読み取り中です...\nしばらくお待ちください。",
        "parse_failed":         "❌ レシートの読み取りに失敗しました。\n別の写真を試してください。",

        # ── Common UI ───────────────────────────────────────
        "btn_cancel":           "❌ キャンセル",
        "btn_back":             "← 戻る",
        "btn_skip":             "スキップ",
        "btn_confirm":          "✅ 確認",
        "btn_edit":             "✏️ 編集",
        "btn_restart":          "🔄 やり直す",
        "btn_add_note":         "📝 メモを追加",
        "btn_select_date":      "📅 日付を選ぶ",
        "btn_other_date":       "📅 別の日付",

        # ── Field labels ────────────────────────────────────
        "label_none":           "なし",
        "label_unknown":        "不明",
        "label_scanned":        "スキャン結果",

        # ── Manual entry ────────────────────────────────────
        "manual_ask_date":      "📅 日付を選択してください",
        "manual_ask_category":  "📂 カテゴリを選択してください\n\n日付: {date}",
        "manual_ask_payment":   "💳 支払方法を選択してください\n\n日付: {date}\nカテゴリ: {category}",
        "manual_ask_amount":    "💴 金額を入力してください\n\n日付: {date}\nカテゴリ: {category}\n支払方法: {payment}\n\n例: 1200",
        "manual_ask_note":      "📝 メモを追加しますか？",
        "manual_ask_confirm":   "以下の内容で登録しますか？\n\n日付: {date}\nカテゴリ: {category}\n支払方法: {payment}\n金額: {amount}\nメモ: {note}",

        # ── Receipt review ──────────────────────────────────
        "receipt_review":       "🧾 {store}\n\n日付: {date}\nカテゴリ: {category}\n支払方法: {payment}\n金額: {amount}\nメモ: {note}\n\n内容を確認してください",
        "receipt_ask_date":     "📅 日付を確認してください\n\n{label_scanned}: {date}",
        "receipt_ask_category": "📂 カテゴリを確認してください\n\n{label_scanned}: {category}",
        "receipt_ask_payment":  "💳 支払方法を確認してください\n\n{label_scanned}: {payment}",
        "receipt_ask_amount":   "💴 金額を確認してください\n\n{label_scanned}: {amount}",
        "receipt_ask_note":     "📝 メモを追加しますか？",
        "receipt_ask_confirm":  "以下の内容で登録しますか？\n\n日付: {date}\nカテゴリ: {category}\n支払方法: {payment}\n金額: {amount}\nメモ: {note}",

        # ── Input prompts ───────────────────────────────────
        "enter_amount_prompt":  "💴 金額を入力してください\n\n例: 1200",
        "enter_note_prompt":    "📝 メモを入力してください",

        # ── Save result ─────────────────────────────────────
        "saved_ok":             "✅ 登録しました！\n\n日付: {date}\nカテゴリ: {category}\n支払方法: {payment}\n金額: {amount}\nメモ: {note}",
        "save_failed":          "❌ 保存に失敗しました。もう一度お試しください。",

        # ── Errors / system ─────────────────────────────────
        "cancelled":            "キャンセルしました ✅",
        "session_expired":      "⏱ 入力セッションが期限切れです。もう一度始めてください。",
        "session_expired_receipt": "⏱ セッションが期限切れです。レシートをもう一度送ってください。",
        "invalid_amount":       "❌ 金額は数字で入力してください。\n例: 1200",
        "invalid_note":         "メモを入力するか、「スキップ」を選択してください。",
        "invalid_action":       "❌ 操作が正しくありません。レシートをもう一度送ってください。",
        "invalid_action_manual":"❌ 入力状態が正しくありません。「手動で入力」からもう一度始めてください。",
        "restart_receipt":      "最初からやり直します。レシートをもう一度送ってください。",
        "date_error":           "❌ 日付を取得できませんでした。もう一度お試しください。",
        "category_error":       "❌ カテゴリを取得できませんでした。もう一度お試しください。",
        "payment_error":        "❌ 支払方法を取得できませんでした。もう一度お試しください。",
        "unknown_message":      "💡 レシートの写真を送るか「使い方」と入力してください",

        # ── How to use ──────────────────────────────────────
        "how_to_use": (
            "📖 使い方\n\n"
            "1️⃣ レシートを写真で送る 🧾\n"
            "   → AIが自動で読み取ります！\n\n"
            "2️⃣ 内容を確認・修正する ✅\n"
            "   日付 · カテゴリ · 金額 · 支払方法\n\n"
            "3️⃣ 手入力もできます ✏️\n"
            "   メニュー →「手動で入力」\n\n"
            "4️⃣ 支出を確認する 📊\n"
            "   メニュー →「マイプロフィール」\n"
            "   月別・カテゴリ別で集計表示！\n\n"
            "━━━━━━━━━━━━\n"
            "💡 言語変更:「言語変更」と送信"
        ),

        # ── Rate limiting ───────────────────────────────────
        "rate_limited_text":    "少しメッセージが多すぎます。少し待ってからもう一度お試しください 🙏",
        "rate_limited_image":   "画像の送信が多すぎます。少し待ってからもう一度レシートを送ってください 🙏",
        "receipt_already_processing":"前のレシートをまだ処理中です。少し待ってください 🙏",
    },

    "en": {
        # ── Language selection ──────────────────────────────
        # lang_select / lang_btn_* intentionally omitted — always called with lang="ja"
        "lang_saved_en":        "🇬🇧 Language set to English!",

        # ── Photo processing ────────────────────────────────
        "processing":           "📷 Reading your receipt...\nThis may take a few seconds.",
        "parse_failed":         "❌ Failed to read the receipt.\nPlease try a clearer photo.",

        # ── Common UI ───────────────────────────────────────
        "btn_cancel":           "❌ Cancel",
        "btn_back":             "← Back",
        "btn_skip":             "Skip",
        "btn_confirm":          "✅ Confirm",
        "btn_edit":             "✏️ Edit",
        "btn_restart":          "🔄 Restart",
        "btn_add_note":         "📝 Add note",
        "btn_select_date":      "📅 Select date",
        "btn_other_date":       "📅 Other date",

        # ── Field labels ────────────────────────────────────
        "label_none":           "None",
        "label_unknown":        "Unknown",
        "label_scanned":        "Scanned",

        # ── Manual entry ────────────────────────────────────
        "manual_ask_date":      "📅 Please select a date",
        "manual_ask_category":  "📂 Please choose a category\n\nDate: {date}",
        "manual_ask_payment":   "💳 Please choose a payment method\n\nDate: {date}\nCategory: {category}",
        "manual_ask_amount":    "💴 Please enter the amount\n\nDate: {date}\nCategory: {category}\nPayment: {payment}\n\nExample: 1200",
        "manual_ask_note":      "📝 Would you like to add a note?",
        "manual_ask_confirm":   "Save this entry?\n\nDate: {date}\nCategory: {category}\nPayment: {payment}\nAmount: {amount}\nNote: {note}",

        # ── Receipt review ──────────────────────────────────
        "receipt_review":       "🧾 {store}\n\nDate: {date}\nCategory: {category}\nPayment: {payment}\nAmount: {amount}\nNote: {note}\n\nPlease review your receipt",
        "receipt_ask_date":     "📅 Confirm the date\n\n{label_scanned}: {date}",
        "receipt_ask_category": "📂 Confirm the category\n\n{label_scanned}: {category}",
        "receipt_ask_payment":  "💳 Confirm payment method\n\n{label_scanned}: {payment}",
        "receipt_ask_amount":   "💴 Confirm the amount\n\n{label_scanned}: {amount}",
        "receipt_ask_note":     "📝 Would you like to add a note?",
        "receipt_ask_confirm":  "Save this entry?\n\nDate: {date}\nCategory: {category}\nPayment: {payment}\nAmount: {amount}\nNote: {note}",

        # ── Input prompts ───────────────────────────────────
        "enter_amount_prompt":  "💴 Please enter the amount\n\nExample: 1200",
        "enter_note_prompt":    "📝 Please type your note",

        # ── Save result ─────────────────────────────────────
        "saved_ok":             "✅ Saved!\n\nDate: {date}\nCategory: {category}\nPayment: {payment}\nAmount: {amount}\nNote: {note}",
        "save_failed":          "❌ Failed to save. Please try again.",

        # ── Errors / system ─────────────────────────────────
        "cancelled":            "Cancelled ✅",
        "session_expired":      "⏱ Session expired. Please start again.",
        "session_expired_receipt": "⏱ Session expired. Please send the receipt again.",
        "invalid_amount":       "❌ Please enter a number.\nExample: 1200",
        "invalid_note":         "Please type a note or tap Skip.",
        "invalid_action":       "❌ Invalid action. Please send the receipt again.",
        "invalid_action_manual":"❌ Invalid state. Please tap Manual Entry to start again.",
        "restart_receipt":      "Starting over. Please send the receipt again.",
        "date_error":           "❌ Could not get the date. Please try again.",
        "category_error":       "❌ Could not get the category. Please try again.",
        "payment_error":        "❌ Could not get the payment method. Please try again.",
        "unknown_message":      "💡 Send a receipt photo or type \"help\"",

        # ── How to use ──────────────────────────────────────
        "how_to_use": (
            "📖 How to use\n\n"
            "1️⃣ Snap a receipt photo 🧾\n"
            "   → AI reads it automatically!\n\n"
            "2️⃣ Review & edit the details ✅\n"
            "   Date · Category · Amount · Payment\n\n"
            "3️⃣ Manual entry available ✏️\n"
            "   Menu → \"Manual Entry\"\n\n"
            "4️⃣ Track your spending 📊\n"
            "   Menu → \"My Profile\"\n"
            "   Monthly breakdown by category!\n\n"
            "━━━━━━━━━━━━\n"
            "💡 Change language: type \"change language\""
        ),

        # ── Rate limiting ───────────────────────────────────
        "rate_limited_text":    "You're sending messages a bit too quickly. Please wait a moment and try again 🙏",
        "rate_limited_image":   "You're sending images too quickly. Please wait a moment before sending another receipt 🙏",
        "receipt_already_processing":"I'm still processing your previous receipt. Please wait a moment 🙏",
    },
}


def t(key: str, lang: str = "ja", **kwargs) -> str:
    """Get a translated string. Falls back to Japanese if key missing in English."""
    text = _S.get(lang, _S["ja"]).get(key)
    if text is None:
        text = _S["ja"].get(key, key)
    return text.format(**kwargs) if kwargs else text
