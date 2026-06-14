#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import requests
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# =========================== تنظیمات ===========================
LOG_URL = "https://raw.githubusercontent.com/alipoorkaramali/youtube-news-watcher/main/logs/new_videos.txt"
STATE_FILE = "State/processed.txt"
MEGA_LOG_FILE = Path("State/mega_upload_log.txt")

REPO_OWNER = "alipoorkaramali"
REPO_NAME = "youtube-SoundCloud-downloader"
WORKFLOW_FILE = "Multi-Platform-Downloader-auto-Mega.yml"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_PAT1 = os.environ.get("GH_PAT1", "")
TOKEN = GH_PAT1 if GH_PAT1 else GITHUB_TOKEN

AUTO_FOLDER = "news_downloads"
MEGA_FOLDER = "YoutubeNews"
QUALITY = "best"
SPLIT_CHOICE = "single"
# ================================================================

def load_processed_hashes():
    if not Path(STATE_FILE).exists():
        return set()
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def save_processed_hashes(hashes):
    Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        for h in hashes:
            f.write(h + "\n")

def load_existing_titles_from_mega_log():
    if not MEGA_LOG_FILE.exists():
        return set()
    with open(MEGA_LOG_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    titles = set()
    for match in re.findall(r'^File\(s\):\s*(.+)$', content, re.MULTILINE):
        for fname in match.split(','):
            titles.add(fname.strip())
    return titles

def add_new_titles_to_mega_log(new_titles):
    if not new_titles:
        return
    MEGA_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MEGA_LOG_FILE, "a", encoding="utf-8") as f:
        for title in new_titles:
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            f.write(f"\n[{now_utc}]\n")
            f.write(f"Platform: auto-detected\n")
            f.write(f"URL: (triggered by check_and_trigger)\n")
            f.write(f"Mega folder: {MEGA_FOLDER}\n")
            f.write(f"Local folder: {AUTO_FOLDER}\n")
            f.write(f"File(s): {title}\n")
            f.write(f"Split: {SPLIT_CHOICE}\n")
            f.write("---\n")

def extract_info(line: str):
    parts = line.split(" | ")
    if len(parts) < 4:
        return None
    platform = parts[1].strip()
    url = parts[-1].strip()
    if platform not in ("youtube", "soundcloud"):
        if "youtube.com" in url or "youtu.be" in url:
            platform = "youtube"
        elif "soundcloud.com" in url:
            platform = "soundcloud"
        else:
            return None
    title_parts = parts[2:-1]
    title = " | ".join(title_parts).strip() if title_parts else None
    return (platform, title, url)

def normalize_title(title: str) -> str:
    """
    نرمالایز عنوان:
    - حذف کلمات داخل پرانتز یا کروشه
    - حذف کلمات اضافی (audio, official, ...)
    - حذف بخش زمان نسبی (مانند «| 2 hours ago»)
    """
    if not title:
        return ""
    # حذف محتویات داخل پرانتز یا کروشه
    title = re.sub(r'\s*[\(\[].*?[\)\]]\s*', ' ', title)
    # حذف کلمات اضافی
    title = re.sub(r'(?i)\b(audio|official|video|music|clip|lyrics|hd|4k|mp3|download)\b', '', title)
    # حذف بخش زمان نسبی (آخرین part بعد از '|' که شامل hours/minutes/ago است)
    parts = title.split('|')
    if len(parts) > 1:
        last_part = parts[-1].strip()
        if re.search(r'\b(hours?|minutes?|ago)\b', last_part, re.I):
            parts = parts[:-1]  # حذف آخرین بخش
    title = '|'.join(parts).strip()
    # حذف فاصله‌های اضافی
    title = re.sub(r'\s+', ' ', title)
    return title.lower()

def trigger_download(video_url: str, platform: str):
    workflow_id = requests.utils.quote(WORKFLOW_FILE, safe='')
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{workflow_id}/dispatches"
    headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "ref": "main",
        "inputs": {
            "platform": platform,
            "url": video_url,
            "type": "audio",
            "quality": QUALITY,
            "folder": AUTO_FOLDER,
            "mega_folder": MEGA_FOLDER,
            "split_choice": SPLIT_CHOICE
        }
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code == 204:
        print(f"✅ Triggered: {video_url}")
        return True
    else:
        print(f"❌ Failed to trigger {video_url}: {resp.status_code} {resp.text}")
        return False

def main():
    try:
        resp = requests.get(LOG_URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"⚠️ Failed to fetch log: {e}")
        return

    lines = [line.strip() for line in resp.text.splitlines() if line.strip()]
    if not lines:
        print("⚠️ No lines in log.")
        return

    processed_hashes = load_processed_hashes()
    existing_titles = load_existing_titles_from_mega_log()
    seen_norm_titles_in_run = set()
    new_titles_to_add = []
    new_count = 0

    for line in lines:
        info = extract_info(line)
        if not info:
            print(f"⚠️ Can't parse line: {line[:80]}...")
            continue
        platform, title, video_url = info
        if not title:
            print(f"⚠️ No title in line: {line[:80]}")
            continue

        link_hash = hashlib.md5(video_url.encode()).hexdigest()
        if link_hash in processed_hashes:
            continue

        # بررسی تکراری عنوان در لاگ مگا (تاریخچه)
        if title in existing_titles:
            print(f"⏭️ Duplicate title (already in mega log): {title}")
            processed_hashes.add(link_hash)
            continue

        norm_title = normalize_title(title)
        # بررسی تکراری عنوان نرمالایز شده در همین اجرا (برای تشخیص بین یوتیوب و ساندکلاود)
        if norm_title in seen_norm_titles_in_run:
            print(f"⏭️ Duplicate normalized title in this run: {title} -> {norm_title}")
            processed_hashes.add(link_hash)
            continue

        # عنوان جدید است
        print(f"🎧 NEW: {title} ({platform}) - {video_url}")
        seen_norm_titles_in_run.add(norm_title)

        success = trigger_download(video_url, platform)
        if success:
            processed_hashes.add(link_hash)
            new_titles_to_add.append(title)
            new_count += 1
        else:
            seen_norm_titles_in_run.discard(norm_title)

    if new_titles_to_add:
        add_new_titles_to_mega_log(new_titles_to_add)
        print(f"📝 Added {len(new_titles_to_add)} new title(s) to {MEGA_LOG_FILE}")
        existing_titles.update(new_titles_to_add)

    save_processed_hashes(processed_hashes)
    print(f"✅ Processed {new_count} new item(s).")

if __name__ == "__main__":
    main()
