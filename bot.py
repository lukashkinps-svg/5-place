import os
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta

import requests
from flask import Flask, request

app = Flask(__name__)

# ============================================================
# TELEGRAM
# ============================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

CHANNEL = "@movetofrance"

PDF_PATH = "antibes_guide.pdf"

TELEGRAM_CHANNEL_URL = "https://t.me/movetofrance"

YOUTUBE_REAL_ESTATE_URL = (
    "https://www.youtube.com/@movetofrance/search?"
    "query=%D0%BD%D0%B5%D0%B4%D0%B2%D0%B8%D0%B6%D0%B8%D0%BC%D0%BE%D1%81%D1%82%D1%8C"
)

YOUTUBE_MARRIAGE_URL = (
    "https://www.youtube.com/@movetofrance/search?"
    "query=%D0%B1%D1%80%D0%B0%D1%87%D0%BD%D1%8B%D0%B9%20%D0%BA%D0%BE%D0%BD%D1%82%D1%80%D0%B0%D0%BA%D1%82"
)

YOUTUBE_DOCTOR_URL = (
    "https://www.youtube.com/@movetofrance/search?"
    "query=%D0%B2%D1%80%D0%B0%D1%87%20%D1%84%D1%80%D0%B0%D0%BD%D1%86%D0%B8%D1%8F"
)

YOUTUBE_STREAMS_URL = "https://www.youtube.com/@movetofrance/streams"

# ============================================================
# DATABASE
# ============================================================

DB_PATH = "/data/antibes_guide_bot.db"


def db_connection():
    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,

                gift_sent INTEGER NOT NULL DEFAULT 0,
                youtube_sent INTEGER NOT NULL DEFAULT 0,

                youtube_due TEXT,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


def save_user(chat_id, user):
    now = datetime.now(timezone.utc).isoformat()

    with db_connection() as conn:
        conn.execute("""
            INSERT INTO users (
                user_id,
                chat_id,
                username,
                first_name,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT(user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                username = excluded.username,
                first_name = excluded.first_name,
                updated_at = excluded.updated_at
        """, (
            user["id"],
            chat_id,
            user.get("username"),
            user.get("first_name"),
            now,
            now
        ))


def get_user(user_id):
    with db_connection() as conn:
        return conn.execute("""
            SELECT *
            FROM users
            WHERE user_id = ?
        """, (user_id,)).fetchone()


def mark_gift_sent(user_id):
    now = datetime.now(timezone.utc)
    youtube_due = now + timedelta(days=2)

    with db_connection() as conn:
        conn.execute("""
            UPDATE users
            SET gift_sent = 1,
                youtube_due = ?,
                updated_at = ?
            WHERE user_id = ?
        """, (
            youtube_due.isoformat(),
            now.isoformat(),
            user_id
        ))


# ============================================================
# TELEGRAM FUNCTIONS
# ============================================================

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    response = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json=payload,
        timeout=30
    )

    response.raise_for_status()


def send_document(chat_id):
    with open(PDF_PATH, "rb") as pdf:
        response = requests.post(
            f"{TELEGRAM_API}/sendDocument",
            data={
                "chat_id": chat_id,
                "caption": "Ваш мини-гид по Антибу 🤍"
            },
            files={
                "document": pdf
            },
            timeout=60
        )

    response.raise_for_status()


# ============================================================
# SUBSCRIPTION
# ============================================================

def is_subscribed(user_id):
    response = requests.get(
        f"{TELEGRAM_API}/getChatMember",
        params={
            "chat_id": CHANNEL,
            "user_id": user_id
        },
        timeout=30
    )

    data = response.json()

    if not data.get("ok"):
        print("getChatMember error:", data)
        return False

    status = data["result"]["status"]

    return status in [
        "member",
        "administrator",
        "creator"
    ]


def subscription_keyboard():
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Подписаться на канал",
                    "url": TELEGRAM_CHANNEL_URL
                }
            ],
            [
                {
                    "text": "Проверить подписку",
                    "callback_data": "check_subscription"
                }
            ]
        ]
    }


# ============================================================
# FUNNEL
# ============================================================

def send_start_message(chat_id):
    send_message(
        chat_id,
        (
            "Привет! Я Гульнара Галеева.\n\n"
            "Здесь вы можете получить мою памятку "
            "<b>«5 мест в Антибе, которые нельзя пропустить»</b> 🇫🇷\n\n"
            "Чтобы получить её бесплатно:\n\n"
            "1. Подпишитесь на мой Telegram-канал.\n"
            "2. Вернитесь сюда и нажмите <b>«Проверить подписку»</b>.\n\n"
            "После проверки я сразу пришлю мини-гид 👇"
        ),
        subscription_keyboard()
    )


def send_not_subscribed_message(chat_id):
    send_message(
        chat_id,
        (
            "Пока не вижу подписку 👀\n\n"
            "Подпишитесь на мой Telegram-канал и возвращайтесь сюда.\n\n"
            "После этого ещё раз нажмите "
            "<b>«Проверить подписку»</b> — и я сразу пришлю мини-гид."
        ),
        {
            "inline_keyboard": [
                [
                    {
                        "text": "Подписаться на канал",
                        "url": TELEGRAM_CHANNEL_URL
                    }
                ],
                [
                    {
                        "text": "Проверить ещё раз",
                        "callback_data": "check_subscription"
                    }
                ]
            ]
        }
    )


def send_gift(chat_id, user_id):
    send_message(
        chat_id,
        (
            "Готово 💗\n\n"
            "Ловите мой мини-гид "
            "<b>«5 мест в Антибе, которые нельзя пропустить»</b>.\n\n"
            "Внутри — мои любимые места, координаты, карты и контакты: "
            "где устроить настоящий французский обед у моря, "
            "увидеть Пикассо в старинном замке, "
            "найти традиционные цветные лодочки "
            "и посмотреть на Антиб сверху.\n\n"
            "👇 Забрать мини-гид"
        )
    )

    send_document(chat_id)

    mark_gift_sent(user_id)


def send_youtube_message(chat_id):
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "🏠 Купить недвижимость",
                    "url": YOUTUBE_REAL_ESTATE_URL
                }
            ],
            [
                {
                    "text": "💍 Брачный контракт",
                    "url": YOUTUBE_MARRIAGE_URL
                }
            ],
            [
                {
                    "text": "👨‍⚕️ Стать доктором во Франции",
                    "url": YOUTUBE_DOCTOR_URL
                }
            ],
            [
                {
                    "text": "▶️ Все эфиры о Франции",
                    "url": YOUTUBE_STREAMS_URL
                }
            ]
        ]
    }

    send_message(
        chat_id,
        (
            "Ну что, Антиб сохранили? 🇫🇷\n\n"
            "Тогда держите ещё кое-что полезное.\n\n"
            "Я много лет веду «Женсовет» — эфиры, где мы вместе "
            "с экспертами разбираем практические вопросы жизни во Франции.\n\n"
            "Выбрала три выпуска, с которых можно начать:\n\n"
            "🏠 <b>Покупка недвижимости во Франции</b>\n"
            "Нотариус, адвокаты, риелтор и финансовый советник — "
            "большой разбор покупки недвижимости.\n\n"
            "💍 <b>Брачный контракт во Франции</b>\n"
            "Что происходит с имуществом и деньгами в браке — "
            "разбираемся с нотариусом и экспертами.\n\n"
            "👨‍⚕️ <b>Как иностранцу стать доктором во Франции</b>\n"
            "Как подтвердить квалификацию и вернуться в профессию во Франции.\n\n"
            "Выбирайте, что вам сейчас актуальнее 👇"
        ),
        keyboard
    )


# ============================================================
# SCHEDULER
# ============================================================

def process_scheduled_messages():
    while True:
        try:
            now = datetime.now(timezone.utc)

            with db_connection() as conn:
                users = conn.execute("""
                    SELECT *
                    FROM users
                    WHERE gift_sent = 1
                """).fetchall()

            for user in users:
                if (
                    user["youtube_sent"] == 0
                    and user["youtube_due"]
                ):
                    youtube_due = datetime.fromisoformat(
                        user["youtube_due"]
                    )

                    if now >= youtube_due:
                        try:
                            send_youtube_message(
                                user["chat_id"]
                            )

                            with db_connection() as conn:
                                conn.execute("""
                                    UPDATE users
                                    SET youtube_sent = 1,
                                        updated_at = ?
                                    WHERE user_id = ?
                                """, (
                                    now.isoformat(),
                                    user["user_id"]
                                ))

                            print(
                                "YouTube message sent:",
                                user["user_id"]
                            )

                        except Exception as error:
                            print(
                                "YouTube message error:",
                                user["user_id"],
                                repr(error)
                            )

        except Exception as error:
            print(
                "Scheduler error:",
                repr(error)
            )

        time.sleep(60)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return "Antibes guide bot is running", 200


# ============================================================
# TELEGRAM WEBHOOK
# ============================================================

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True) or {}

    try:
        message = update.get("message")

        if message:
            chat_id = message["chat"]["id"]
            user = message["from"]
            text = message.get("text", "")

            save_user(
                chat_id,
                user
            )

            if text.startswith("/start"):
                send_start_message(chat_id)

        callback_query = update.get("callback_query")

        if callback_query:
            chat_id = callback_query["message"]["chat"]["id"]
            user = callback_query["from"]
            callback_data = callback_query.get("data")

            save_user(
                chat_id,
                user
            )

            requests.post(
                f"{TELEGRAM_API}/answerCallbackQuery",
                json={
                    "callback_query_id": callback_query["id"]
                },
                timeout=30
            )

            if callback_data == "check_subscription":
                if is_subscribed(user["id"]):

                    row = get_user(user["id"])

                    if row and row["gift_sent"] == 0:
                        send_gift(
                            chat_id,
                            user["id"]
                        )
                    else:
                        send_message(
                            chat_id,
                            "Мини-гид уже был отправлен вам 🤍"
                        )

                else:
                    send_not_subscribed_message(
                        chat_id
                    )

    except Exception as error:
        print(
            "Telegram webhook error:",
            repr(error)
        )

    return "OK", 200


# ============================================================
# START
# ============================================================

init_db()

scheduler_thread = threading.Thread(
    target=process_scheduled_messages,
    daemon=True
)

scheduler_thread.start()


if __name__ == "__main__":
    port = int(
        os.environ.get(
            "PORT",
            8080
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
