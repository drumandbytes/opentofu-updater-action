#!/usr/bin/env python3
"""Send Telegram notification for version updates."""

import os
import urllib.request
import urllib.parse

token = os.environ["TELEGRAM_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]
report = os.environ.get("REPORT", "")
repo = os.environ.get("REPO", "")

text = f"*OpenTofu Updater* — [{repo}](https://github.com/{repo})\n\n{report}"

data = urllib.parse.urlencode({
    "chat_id": chat_id,
    "text": text,
    "parse_mode": "Markdown",
    "disable_web_page_preview": "true",
}).encode()

req = urllib.request.Request(
    f"https://api.telegram.org/bot{token}/sendMessage",
    data=data,
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    print(f"Telegram: {resp.status}")
