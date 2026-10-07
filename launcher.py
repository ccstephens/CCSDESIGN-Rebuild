from __future__ import annotations
import threading
import time
import webbrowser
import urllib.request
import uvicorn
from backend.app.main import app

HOST="127.0.0.1"
PORT=8000
URL=f"http://{HOST}:{PORT}"

def wait_and_open():
    health=f"{URL}/api/health"
    for _ in range(60):
        try:
            with urllib.request.urlopen(health,timeout=1) as response:
                if response.status==200:
                    webbrowser.open(URL)
                    return
        except Exception:
            time.sleep(0.25)

def main():
    threading.Thread(target=wait_and_open,daemon=True).start()
    uvicorn.run(app,host=HOST,port=PORT,log_level="info")

if __name__=="__main__":
    main()
