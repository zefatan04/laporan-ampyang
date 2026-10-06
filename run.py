"""Jalankan aplikasi: python run.py  ->  http://localhost:8000"""

import os
import threading
import webbrowser

import uvicorn
from dotenv import load_dotenv

load_dotenv()
PORT = int(os.environ.get("AMPYANG_PORT", 8000))

if __name__ == "__main__":
    if os.environ.get("AMPYANG_TANPA_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    # Hanya localhost: data omzet tidak boleh terbuka ke jaringan lain.
    uvicorn.run("app.web:app", host="127.0.0.1", port=PORT, log_level="warning")
