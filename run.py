"""
Main entry point to start both the A2 TV REST API Server and Telegram Bot.
"""

import sys
import threading
import time
from config import API_HOST, API_PORT, BOT_TOKEN, ADMIN_ID
from server import run_server
from bot import run_bot

def print_banner():
    print("=" * 60)
    print(" 🚀 A2 TV Backend API & Telegram Bot Control Panel 🚀 ")
    print("=" * 60)
    print(f"📡 API Server:   http://{API_HOST}:{API_PORT}")
    print(f"🤖 Telegram Bot: {'✅ مفعّل' if (BOT_TOKEN and ':' in BOT_TOKEN and BOT_TOKEN != 'YOUR_TELEGRAM_BOT_TOKEN_HERE') else '⚠️ بانتظار التوكن في .env'}")
    print(f"👑 Super Admin:  {ADMIN_ID if ADMIN_ID else 'غير محدد بعد في .env'}")
    print("=" * 60)

def main():
    print_banner()

    # Start Bot in background thread
    bot_thread = threading.Thread(target=run_bot, name="TelegramBotThread", daemon=True)
    bot_thread.start()

    # Give bot half a second to initialize
    time.sleep(0.5)

    # Start API Web Server in main thread
    try:
        print(f"🌐 بدء تشغيل خادم الـ API على المنفذ {API_PORT}...")
        run_server(host=API_HOST, port=API_PORT)
    except KeyboardInterrupt:
        print("\n🛑 تم إيقاف السيرفر والبوت بنجاح.")
        sys.exit(0)

if __name__ == "__main__":
    main()
