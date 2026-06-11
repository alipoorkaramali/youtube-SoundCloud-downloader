#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import requests
from pathlib import Path
from urllib.parse import urlparse

def download_file(url, output_path):
    """دانلود فایل با requests و ذخیره در مسیر مشخص"""
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"⚠️ دانلود مستقیم ناموفق: {e}")
        return False

def download_with_ytdlp(shortcode, output_dir, cookies_file=None):
    """اجرای yt-dlp برای دانلود پست اینستاگرام"""
    url = f"https://www.instagram.com/p/{shortcode}/"
    cmd = ["yt-dlp", "-o", f"{output_dir}/%(title)s.%(ext)s", url]
    if cookies_file and os.path.exists(cookies_file):
        cmd.extend(["--cookies", cookies_file])
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ yt-dlp خطا: {e.stderr}")
        return False

def main():
    if len(sys.argv) < 2:
        print("❌ استفاده: python download_with_fallback.py <shortcode>")
        sys.exit(1)

    shortcode = sys.argv[1]
    base_dir = Path("instagram_downloads") / shortcode
    base_dir.mkdir(parents=True, exist_ok=True)
    info_json = base_dir / "post_info.json"

    # ---------- مرحله ۱: دانلود از لینک‌های مستقیم داخل JSON ----------
    if info_json.exists():
        print("📄 فایل post_info.json پیدا شد. استخراج لینک‌های مستقیم...")
        with open(info_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # جستجوی لینک‌های احتمالی (display_url, video_url, image_versions2 و...)
        urls_to_download = []
        if "display_url" in data:
            urls_to_download.append(data["display_url"])
        if "video_url" in data:
            urls_to_download.append(data["video_url"])
        # اگر آرایه‌ای از مدیاها باشد
        if "media" in data and isinstance(data["media"], list):
            for media in data["media"]:
                if "url" in media:
                    urls_to_download.append(media["url"])
        # جستجوی بازگشتی ساده در کل دیکشنری (برای یافتن هر لینک اینستاگرامی)
        def find_urls(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    find_urls(v)
            elif isinstance(obj, list):
                for item in obj:
                    find_urls(item)
            elif isinstance(obj, str) and ("cdninstagram.com" in obj or "fbcdn.net" in obj):
                urls_to_download.append(obj)
        find_urls(data)

        # حذف تکراری‌ها
        urls_to_download = list(set(urls_to_download))
        print(f"🔍 {len(urls_to_download)} لینک مستقیم پیدا شد.")

        success = False
        for i, url in enumerate(urls_to_download):
            ext = url.split("?")[0].split(".")[-1] or "mp4"
            filename = f"media_{i+1}.{ext}"
            out_path = base_dir / filename
            if download_file(url, out_path):
                print(f"✅ دانلود شد: {filename}")
                success = True
            else:
                print(f"❌ شکست در دانلود: {url}")
        if success:
            print("🎉 همه فایل‌های قابل دانلود با روش مستقیم دریافت شدند.")
            return
        else:
            print("⚠️ هیچ لینک مستقیمی کار نکرد. رفتن به مرحله yt-dlp...")
    else:
        print("ℹ️ فایل post_info.json وجود ندارد. رفتن به مرحله yt-dlp...")

    # ---------- مرحله ۲: yt-dlp بدون کوکی ----------
    print("🔄 تلاش با yt-dlp (بدون کوکی)...")
    if download_with_ytdlp(shortcode, base_dir):
        print("✅ دانلود با yt-dlp بدون کوکی موفقیت‌آمیز بود.")
        return

    # ---------- مرحله ۳: yt-dlp با کوکی ----------
    cookies_path = os.environ.get("INSTAGRAM_COOKIES_PATH")
    if cookies_path and Path(cookies_path).exists():
        print("🍪 تلاش با yt-dlp + کوکی...")
        if download_with_ytdlp(shortcode, base_dir, cookies_path):
            print("✅ دانلود با کوکی موفقیت‌آمیز بود.")
            return
        else:
            print("❌ حتی با کوکی هم دانلود نشد.")
    else:
        print("⚠️ فایل کوکی در دسترس نیست.")

    print("💥 دانلود با هیچ روشی انجام نشد.")
    sys.exit(1)

if __name__ == "__main__":
    main()
