"""打包入口：启动服务器 + 自动打开浏览器"""
import sys
import os
import webbrowser
import threading
import time
import requests

# Fix: --noconsole 模式下 sys.stderr 为 None，uvicorn 会崩溃
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import uvicorn

# 确保工作目录在 exe 所在位置（打包后也生效）
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

from web_app import app


def open_browser_when_ready():
    """等待服务就绪后打开浏览器"""
    time.sleep(2)
    for _ in range(30):
        try:
            r = requests.get("http://127.0.0.1:8000/api/status", timeout=2)
            if r.status_code == 200:
                webbrowser.open("http://127.0.0.1:8000")
                return
        except Exception:
            pass
        time.sleep(1)


if __name__ == "__main__":
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    uvicorn.run(
        app, host="127.0.0.1", port=8000,
        log_config={
            "version": 1,
            "formatters": {
                "default": {"format": "%(asctime)s %(message)s"},
                "access": {"format": "%(asctime)s %(message)s"},
            },
            "handlers": {
                "default": {"class": "logging.StreamHandler", "formatter": "default", "stream": "ext://sys.stdout"},
                "access": {"class": "logging.StreamHandler", "formatter": "access", "stream": "ext://sys.stdout"},
            },
            "root": {"level": "WARNING", "handlers": ["default"]},
            "loggers": {
                "uvicorn": {"level": "INFO", "handlers": ["default"]},
                "uvicorn.access": {"level": "WARNING", "handlers": ["access"]},
            },
        },
    )
