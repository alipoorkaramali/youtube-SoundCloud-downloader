#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import requests
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

# =========================== تنظیمات ===========================
LOG_URL = "https://raw.githubusercontent.com/alipoorkaramali/youtube-news-watcher/main/logs/new_videos.txt"
STATE_FILE = "State/processed.txt"                 # هش لینک‌های پردازش شده
SEEN_TITLES_FILE = Path("State/seen_titles.txt")   # هش عناوین نرمالایز شده دیده شده (موفق)
FAILED_SC_FILE = Path("State/failed_soundcloud_titles.txt")  # عناوینی که SoundCloud آن‌ها شکست خورده

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

def load_seen_normalized_titles():
    if not SEEN_TITLES_FILE.exists():
        return set()
    with open(SEEN_TITLES_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def save_seen_normalized_title(norm_hash):
    SEEN_TITLES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_TITLES_FILE, "a", encoding="utf-8") as f:
        f.write(norm_hash + "\n")

def load_failed_soundcloud_titles():
    if not FAILED_SC_FILE.exists():
        return set()
    with open(FAILED_SC_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def save_failed_soundcloud_title(norm_hash):
    FAILED_SC_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FAILED_SC_FILE, "a", encoding="utf-8") as f:
        f.write(norm_hash + "\n")

def remove_failed_soundcloud_title(norm_hash):
    """حذف یک هش از فایل شکست SoundCloud (بازنویسی فایل)"""
    if not FAILED_SC_FILE.exists():
        return
    titles = load_failed_soundcloud_titles()
    if norm_hash in titles:
        titles.remove(norm_hash)
        with open(FAILED_SC_FILE, "w", encoding="utf-8") as f:
            for h in titles:
                f.write(h + "\n")

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
    if not title:
        return ""
    # حذف داخل پرانتز/کروشه
    title = re.sub(r'\s*[\(\[].*?[\)\]]\s*', ' ', title)
    # حذف کلمات اضافی
    title = re.sub(r'(?i)\b(audio|official|video|music|clip|lyrics|hd|4k|mp3|download)\b', '', title)
    # حذف بخش زمان نسبی (| 2 hours ago)
    parts = title.split('|')
    if len(parts) > 1:
        last_part = parts[-1].strip()
        if re.search(r'\b(hours?|minutes?|ago)\b', last_part, re.I):
            parts = parts[:-1]
    title = '|'.join(parts).strip()
    title = re.sub(r'\s+', ' ', title)
    title = re.sub(r'\s*\|\s*', '|', title)
    return hashlib.md5(title.lower().encode('utf-8')).hexdigest()

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
    # دریافت لاگ خبری
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

    # داده‌های پایدار
    processed_hashes = load_processed_hashes()
    seen_norm_hashes = load_seen_normalized_titles()
    failed_sc_hashes = load_failed_soundcloud_titles()

    # جمع‌آوری اطلاعات برای هر عنوان نرمالایز شده
    title_map = defaultdict(list)  # norm_hash -> list of (platform, title, url, raw_title)
    for line in lines:
        info = extract_info(line)
        if not info:
            continue
        platform, raw_title, url = info
        if not raw_title:
            continue
        norm_hash = normalize_title(raw_title)
        if not norm_hash:
            continue
        title_map[norm_hash].append((platform, raw_title, url))

    seen_in_run = set()   # هش عناوینی که در این اجرا ارسال شده‌اند
    new_titles_to_add = []  # برای ثبت در seen_titles (موفق)
    new_count = 0

    for norm_hash, items in title_map.items():
        # اگر قبلاً در تاریخچه دیده شده، رد کن
        if norm_hash in seen_norm_hashes:
            print(f"⏭️ Already seen (global): {norm_hash}")
            # لینک‌های آن را هم به processed_hashes اضافه کن تا دیگر نیایند
            for _, _, url in items:
                link_hash = hashlib.md5(url.encode()).hexdigest()
                processed_hashes.add(link_hash)
            continue

        # اگر در همین اجرا قبلاً ارسال شده، رد کن
        if norm_hash in seen_in_run:
            print(f"⏭️ Already sent in this run: {norm_hash}")
            for _, _, url in items:
                link_hash = hashlib.md5(url.encode()).hexdigest()
                processed_hashes.add(link_hash)
            continue

        # تعیین اولویت: اگر SoundCloud در فایل شکست باشد، YouTube را انتخاب کن
        # در غیر این صورت اولویت با SoundCloud است
        selected_platform = None
        selected_title = None
        selected_url = None
        selected_raw_title = None

        # اگر این عنوان در فایل شکست SoundCloud هست → به سراغ YouTube برو
        if norm_hash in failed_sc_hashes:
            # پیدا کردن آیتم YouTube
            for platform, raw_title, url in items:
                if platform == "youtube":
                    selected_platform = platform
                    selected_raw_title = raw_title
                    selected_url = url
                    selected_title = raw_title
                    break
            # اگر YouTube پیدا نشد، شاید فقط SoundCloud هست (که باز هم نمی‌خواهیم)
            if not selected_platform:
                print(f"⚠️ Title {norm_hash} is in failed SC but no YouTube link found. Skipping.")
                continue
        else:
            # اولویت با SoundCloud
            for platform, raw_title, url in items:
                if platform == "soundcloud":
                    selected_platform = platform
                    selected_raw_title = raw_title
                    selected_url = url
                    selected_title = raw_title
                    break
            # اگر SoundCloud نبود، YouTube را انتخاب کن
            if not selected_platform:
                for platform, raw_title, url in items:
                    if platform == "youtube":
                        selected_platform = platform
                        selected_raw_title = raw_title
                        selected_url = url
                        selected_title = raw_title
                        break
            # اگر هیچکدام (فقط موارد دیگر) – نباید شود
            if not selected_platform:
                continue

        # بررسی تکراری لینک (هش) برای لینک انتخابی
        link_hash = hashlib.md5(selected_url.encode()).hexdigest()
        if link_hash in processed_hashes:
            # این لینک قبلاً پردازش شده (حتی اگر عنوان جدید باشد)
            continue

        # عنوان جدید است
        print(f"🎧 NEW (priority: {selected_platform}): {selected_raw_title} - {selected_url}")
        seen_in_run.add(norm_hash)

        # ارسال درخواست
        success = trigger_download(selected_url, selected_platform)

        if success:
            # موفقیت آمیز: ذخیره هش عنوان در تاریخچه و هش لینک در processed
            save_seen_normalized_title(norm_hash)
            seen_norm_hashes.add(norm_hash)
            processed_hashes.add(link_hash)
            new_titles_to_add.append(selected_title)  # برای لاگ (اختیاری)
            new_count += 1
            # اگر این عنوان قبلاً در فایل شکست SoundCloud بود و حالا با YouTube موفق شد، آن را از فایل شکست حذف کن
            if norm_hash in failed_sc_hashes:
                remove_failed_soundcloud_title(norm_hash)
                print(f"✅ Removed {norm_hash} from failed SC list because YouTube succeeded.")
        else:
            # شکست در ارسال
            if selected_platform == "soundcloud":
                # ثبت شکست SoundCloud برای این عنوان
                save_failed_soundcloud_title(norm_hash)
                print(f"⚠️ Recorded failure for SoundCloud title: {norm_hash}")
                # هش لینک را ذخیره نمی‌کنیم تا دفعه بعد دوباره تلاش شود، ولی عنوان را در seen_in_run نگه می‌داریم تا در این اجرا دوباره تلاش نشود
            else:
                # اگر YouTube با شکست مواجه شد، فعلاً هیچ کاری نمی‌کنیم (شاید بعداً دوباره تلاش شود)
                print(f"❌ YouTube also failed for {norm_hash}")

    # ذخیره هش لینک‌های پردازش شده (موفق و آنهایی که رد شده‌اند)
    save_processed_hashes(processed_hashes)

    print(f"✅ Processed {new_count} new item(s).")

if __name__ == "__main__":
    main()
