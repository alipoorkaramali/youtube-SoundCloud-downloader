#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import json
import subprocess
import requests
import zipfile
from pathlib import Path
from io import BytesIO

def download_with_ytdlp(url, output_path):
    print(f"🎬 تلاش با yt-dlp...")
    cmd = ["yt-dlp", "--no-playlist", "-o", output_path, url]
    try:
        subprocess.run(cmd, check=False, capture_output=True, text=True)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            print(f"✅ موفقیت با yt-dlp")
            return True
        else:
            print(f"⚠️ yt-dlp فایلی ذخیره نکرد")
            return False
    except Exception as e:
        print(f"⚠️ خطا: {e}")
        return False

def download_from_media_urls(media_urls, download_dir, shortcode, post_type):
    if not media_urls:
        return False
    print(f"🖼️ دانلود از media_urls...")
    if len(media_urls) > 1 or post_type == "CAROUSEL_ALBUM":
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
            for idx, url in enumerate(media_urls, start=1):
                try:
                    ext = 'jpg' if '.mp4' not in url and 'video' not in url else 'mp4'
                    fname = f"{shortcode}_{idx}.{ext}"
                    resp = requests.get(url, stream=True, timeout=30)
                    resp.raise_for_status()
                    zip_file.writestr(fname, resp.content)
                    print(f"  - {fname} اضافه شد")
                except Exception as e:
                    print(f"  ❌ خطا: {e}")
        zip_path = download_dir / f"{shortcode}.zip"
        with open(zip_path, 'wb') as f:
            f.write(zip_buffer.getvalue())
        print(f"✅ ZIP ذخیره شد: {zip_path}")
        return True
    else:
        url = media_urls[0]
        ext = 'jpg' if '.mp4' not in url and 'video' not in url else 'mp4'
        file_path = download_dir / f"{shortcode}.{ext}"
        try:
            resp = requests.get(url, stream=True, timeout=30)
            resp.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"✅ فایل ذخیره شد: {file_path}")
            return True
        except Exception as e:
            print(f"❌ خطا: {e}")
            return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python download_instagram_by_index.py <shortcode>")
        sys.exit(1)
    shortcode = sys.argv[1]

    # ابتدا سعی می‌کنیم اطلاعات پست را از طریق Apify JSON بگیریم (اگر موجود باشد)
    json_file = Path("instagram_posts.json")
    post_data = None
    if json_file.exists():
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for p in data.get('recent_posts', []):
                if p.get('shortcode') == shortcode:
                    post_data = p
                    break

    if post_data:
        post_url = post_data.get('url')
        post_type = post_data.get('post_type')
        caption = post_data.get('caption', '')
        media_urls = post_data.get('media_urls', [])
        print(f"📸 پیدا شد در JSON: {shortcode} - {post_type}")
    else:
        # اگر در JSON نبود، از خود shortcode لینک بساز
        post_url = f"https://www.instagram.com/p/{shortcode}/"
        post_type = "UNKNOWN"
        caption = ""
        media_urls = []
        print(f"🌐 استفاده از URL: {post_url}")

    download_dir = Path("instagram_downloads") / shortcode
    download_dir.mkdir(parents=True, exist_ok=True)

    downloaded = False

    # اول yt-dlp
    ytdlp_path = download_dir / f"{shortcode}_ytdlp.mp4"
    if download_with_ytdlp(post_url, str(ytdlp_path)):
        downloaded = True
        with open(download_dir / "info.txt", 'w', encoding='utf-8') as f:
            f.write(f"Method: yt-dlp\nShortcode: {shortcode}\nURL: {post_url}\nCaption: {caption}\n")
    else:
        # اگر yt-dlp موفق نبود و media_urls داریم
        if media_urls:
            if download_from_media_urls(media_urls, download_dir, shortcode, post_type):
                downloaded = True
                with open(download_dir / "info.txt", 'w', encoding='utf-8') as f:
                    f.write(f"Method: media_urls\nShortcode: {shortcode}\nURL: {post_url}\nCaption: {caption}\n")
        else:
            # آخرین تلاش: شاید پست فقط یک عکس باشد و media_urls نداشته باشیم؟
            print("❌ هیچ روشی جواب نداد")
            with open(download_dir / "error.txt", 'w', encoding='utf-8') as f:
                f.write(f"Failed: {shortcode}\nURL: {post_url}\n")
            sys.exit(1)

    if downloaded:
        print(f"🎉 دانلود موفق: {shortcode}")
    else:
        print(f"❌ دانلود ناموفق")
        sys.exit(1)

if __name__ == '__main__':
    main()