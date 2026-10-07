from __future__ import annotations
import threading
import time
import webbrowser
import urllib.request
import socket
import sys
import os
import ctypes
import traceback
from pathlib import Path
import uvicorn
from backend.app.main import app

HOST="127.0.0.1"
PORT=8000
URL=f"http://{HOST}:{PORT}"
LOG_DIR=Path(__file__).resolve().parent if not getattr(sys,"frozen",False) else Path(os.environ.get("LOCALAPPDATA",Path.home()))/"CCSDESIGN Rebuild"
LOG_FILE=LOG_DIR/"startup-error.log"

def log_error(message):
    try:
        LOG_DIR.mkdir(parents=True,exist_ok=True)
        LOG_FILE.write_text(message,encoding="utf-8")
    except Exception:
        pass

def fatal(message):
    log_error(message)
    if sys.platform=="win32" and os.environ.get("CCSDESIGN_NO_DIALOG")!="1":
        try: ctypes.windll.user32.MessageBoxW(None,message,"CCSDESIGN Rebuild",0x10)
        except Exception: pass
    raise SystemExit(message)

def wait_and_open():
    health=f"{URL}/api/health"
    for _ in range(60):
        try:
            with urllib.request.urlopen(health,timeout=1) as response:
                if response.status==200:
                    if os.environ.get("CCSDESIGN_NO_BROWSER")!="1": webbrowser.open(URL)
                    return
        except Exception:
            time.sleep(0.25)

def main():
    try:
        with urllib.request.urlopen(f"{URL}/api/health",timeout=1) as response:
            if response.status==200:
                if os.environ.get("CCSDESIGN_NO_BROWSER")!="1": webbrowser.open(URL)
                return
    except Exception:
        pass
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        if sock.connect_ex((HOST,PORT))==0:
            fatal("Port 8000 is already in use by another application. Close that application, then start CCSDESIGN Rebuild again.")
    threading.Thread(target=wait_and_open,daemon=True).start()
    uvicorn.run(app,host=HOST,port=PORT,log_level="info",log_config=None if getattr(sys,"frozen",False) else uvicorn.config.LOGGING_CONFIG)

if __name__=="__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        details=traceback.format_exc()
        log_error(details)
        if sys.platform=="win32" and os.environ.get("CCSDESIGN_NO_DIALOG")!="1":
            try: ctypes.windll.user32.MessageBoxW(None,f"CCSDESIGN Rebuild could not start.\n\nDetails were written to:\n{LOG_FILE}","CCSDESIGN Rebuild",0x10)
            except Exception: pass
        raise
