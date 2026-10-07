from __future__ import annotations
import threading
import time
import webbrowser
import urllib.request
import socket
import sys
import ctypes
import uvicorn
from backend.app.main import app

HOST="127.0.0.1"
PORT=8000
URL=f"http://{HOST}:{PORT}"

def fatal(message):
    if sys.platform=="win32":
        try: ctypes.windll.user32.MessageBoxW(None,message,"CCSDESIGN Rebuild",0x10)
        except Exception: pass
    raise SystemExit(message)

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
    try:
        with urllib.request.urlopen(f"{URL}/api/health",timeout=1) as response:
            if response.status==200:
                webbrowser.open(URL)
                return
    except Exception:
        pass
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        if sock.connect_ex((HOST,PORT))==0:
            fatal("Port 8000 is already in use by another application. Close that application, then start CCSDESIGN Rebuild again.")
    threading.Thread(target=wait_and_open,daemon=True).start()
    uvicorn.run(app,host=HOST,port=PORT,log_level="info")

if __name__=="__main__":
    main()
