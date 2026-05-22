# ==============================================================
# main.py
# Master entry point.
# Starts the FastAPI backend via uvicorn and opens the UI
# in the default browser automatically.
# Run with: python main.py  (or via ./run.sh)
# ==============================================================

import os
import time
import threading
import webbrowser
import uvicorn
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

HOST = os.getenv("APP_HOST", "127.0.0.1")
PORT = int(os.getenv("APP_PORT", "8000"))
URL  = f"http://{HOST}:{PORT}"


def open_browser():
    """Wait briefly for the server to start, then open the browser."""
    time.sleep(1.5)
    webbrowser.open(URL)
    print(f"[Main] Opened browser at {URL}")


if __name__ == "__main__":
    print(f"[Main] Starting Video Pipeline at {URL}")

    # Open browser in a background thread so it doesn't block uvicorn
    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "backend.api:app",
        host=HOST,
        port=PORT,
        reload=False,       # Set True during development for auto-reload
        log_level="info"
    )
