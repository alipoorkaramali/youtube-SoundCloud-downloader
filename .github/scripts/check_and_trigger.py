import os
import re
import requests
import hashlib
from pathlib import Path

# ============= تنظیمات =============
LOG_URL = "https://raw.githubusercontent.com/alipoorkaramali/youtube-news-watcher/main/logs/new_videos.txt"
STATE_FILE = "processed.txt"
TITLE_STATE_FILE = "processed_titles.txt"

REPO_OWNER = "alipoorkaramali"
REPO_NAME = "youtube-SoundCloud-downloader"
WORKFLOW_FILE = "Multi-Platform-Downloader-auto-Mega.yml"   # ورک‌فلو جدید مگا
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# پارامترهای ورودی به ورک‌فلو جدید
AUTO_FOLDER = "news_downloads"
MEGA_FOLDER = "YoutubeNews"
QUALITY = "best"
SPLIT_CHOICE = "single"
# ==================================

def load_processed_hashes():
    if not Path(STATE_FILE).exists():
        return set()
    with open(STATE_FILE) as f:
        return set(line.strip() for line in f if line.strip())

def save_processed_hashes(hashes):
    with open(STATE_FILE, "w") as f:
        for h in hashes:
            f.write(h + "\n")

def load_processed_titles():
    if not Path(TITLE_STATE_FILE).exists():
        return set()
    with open(TITLE_STATE_FILE, encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def add_processed_title(title):
    with open(TITLE_STATE_FILE, "a", encoding='utf-8') as f:
        f.write(title + "\n")

def extract_info(line: str):
    """
    استخراج (platform, title, url) از خط لاگ
    فرمت خط: timestamp | platform | عنوان | relative_time | url
    """
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
    # عنوان ممکن است شامل " | " باشد، پس همه بخش‌های بین index2 تا -1 را با هم ترکیب می‌کنیم
    title_parts = parts[2:-1]
    title = " | ".join(title_parts).strip() if title_parts else None
    return (platform, title, url)

def normalize_title(title: str) -> str:
    """نرمالایز عنوان برای جلوگیری از تشخیص تکراری بین پلتفرم‌ها"""
    if not title:
        return ""
    # حذف محتوای داخل پرانتز یا کروشه
    title = re.sub(r'\s*[\(\[].*?[\)\]]\s*', ' ', title)
    # حذف کلمات رایج اضافی
    title = re.sub(r'(?i)\b(audio|official|video|music|clip|lyrics|hd|4k|mp3|download)\b', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip().lower()

def trigger_download(video_url: str, platform: str):
    """فعال‌سازی ورک‌فلو جدید مگا از طریق GitHub API"""
    workflow_id = requests.utils.quote(WORKFLOW_FILE, safe='')
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{workflow_id}/dispatches"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
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
        print(f"❌ Failed {video_url}: {resp.status_code} {resp.text}")
        return False

def main():
    resp = requests.get(LOG_URL)
    if resp.status_code != 200:
        print(f"⚠️ Failed to fetch log: {resp.status_code}")
        return

    lines = [line.strip() for line in resp.text.splitlines() if line.strip()]
    processed_hashes = load_processed_hashes()
    processed_titles = load_processed_titles()
    seen_normalized_titles = set()
    new_count = 0

    for line in lines:
        info = extract_info(line)
        if not info:
            print(f"⚠️ Can't parse line: {line[:80]}...")
            continue
        platform, title, video_url = info

        # جلوگیری از تکراری لینک
        link_hash = hashlib.md5(video_url.encode()).hexdigest()
        if link_hash in processed_hashes:
            continue

        # جلوگیری از تکراری عنوان دقیق
        if title and title in processed_titles:
            print(f"⏭️ Duplicate title (from file): {title}")
            processed_hashes.add(link_hash)
            continue

        # جلوگیری از تکراری عنوان نرمالایز شده در همین اجرا
        norm_title = normalize_title(title) if title else None
        if norm_title and norm_title in seen_normalized_titles:
            print(f"⏭️ Duplicate normalized title in this run: {title} -> {norm_title}")
            processed_hashes.add(link_hash)
            continue

        print(f"🎧 New item: {video_url} ({platform})")
        success = trigger_download(video_url, platform)

        if success:
            processed_hashes.add(link_hash)
            if title:
                processed_titles.add(title)
                add_processed_title(title)
            if norm_title:
                seen_normalized_titles.add(norm_title)
            new_count += 1
        # اگر dispatch ناموفق بود، لینک را ذخیره نمی‌کنیم تا دفعه بعد دوباره تلاش شود

    save_processed_hashes(processed_hashes)
    print(f"✅ Processed {new_count} new item(s).")

if __name__ == "__main__":
    main()
