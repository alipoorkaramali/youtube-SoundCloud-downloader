#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import subprocess
import sys
import requests
import zipfile
from pathlib import Path
from io import BytesIO

def download_with_ytdlp(url, output_path):
    """تلاش برای دانلود با yt-dlp (مناسب برای ویدیو و عکس)"""
    print(f"🎬 تلاش برای دانلود با yt-dlp...")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-o", output_path,
        url
    ]
    try:
        # '--ignore-errors' را اضافه می‌کنیم تا در صورت خطا ادامه دهد
        subprocess.run(cmd, check=False, capture_output=True, text=True)
        # بررسی می‌کنیم که آیا فایل واقعاً دانلود شده است
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            print(f"✅ دانلود با yt-dlp موفقیت‌آمیز بود.")
            return True
        else:
            print(f"⚠️ yt-dlp فایلی دانلود نکرد.")
            return False
    except Exception as e:
        print(f"⚠️ خطا در yt-dlp: {e}")
        return False

def download_from_media_urls(media_urls, download_dir, shortcode, post_type):
    """دانلود از آرایه media_urls (برای عکس‌ها و Carousel‌ها)"""
    if not media_urls:
        return False

    print(f"🖼️ تلاش برای دانلود از روی media_urls...")

    # اگر تعداد رسانه‌ها بیشتر از یک است یا نوع Carousel است، همه را دانلود و Zip کن
    if len(media_urls) > 1 or post_type == "CAROUSEL_ALBUM":
        print(f"📦 پست از نوع Carousel با {len(media_urls)} رسانه. در حال فشرده‌سازی به ZIP...")
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
            for idx, url in enumerate(media_urls, start=1):
                try:
                    # تعیین پسوند فایل (jpg یا mp4)
                    ext = 'jpg'
                    if '.mp4' in url or 'video' in url:
                        ext = 'mp4'
                    file_name = f"{shortcode}_{idx}.{ext}"
                    
                    resp = requests.get(url, stream=True, timeout=30)
                    resp.raise_for_status()
                    zip_file.writestr(file_name, resp.content)
                    print(f"  - افزودن {file_name} به ZIP")
                except Exception as e:
                    print(f"  ❌ خطا در دانلود {url}: {e}")
        
        zip_path = download_dir / f"{shortcode}.zip"
        with open(zip_path, 'wb') as f:
            f.write(zip_buffer.getvalue())
        print(f"✅ ZIP ذخیره شد: {zip_path}")
        return True

    # اگر فقط یک رسانه است (مثلاً یک عکس ساده)
    else:
        single_url = media_urls[0]
        # تعیین پسوند فایل
        ext = 'jpg'
        if '.mp4' in single_url or 'video' in single_url:
            ext = 'mp4'
        
        file_path = download_dir / f"{shortcode}.{ext}"
        try:
            resp = requests.get(single_url, stream=True, timeout=30)
            resp.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"✅ فایل ذخیره شد: {file_path}")
            return True
        except Exception as e:
            print(f"❌ خطا در دانلود عکس: {e}")
            return False

def main():
    # دریافت شماره پست از کاربر
    index_str = os.environ.get('POST_INDEX', '').strip()
    if not index_str:
        print("❌ POST_INDEX is required")
        sys.exit(1)

    try:
        index = int(index_str) - 1
    except ValueError:
        print("❌ POST_INDEX must be a number")
        sys.exit(1)

    # خواندن فایل JSON
    json_file = Path("instagram_posts.json")
    if not json_file.exists():
        print("❌ instagram_posts.json not found. Run fetch workflow first.")
        sys.exit(1)

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    posts = data.get('recent_posts', [])
    if not posts:
        print("❌ No posts found")
        sys.exit(1)

    if index < 0 or index >= len(posts):
        print(f"❌ Invalid index. Choose 1..{len(posts)}")
        sys.exit(1)

    post = posts[index]
    shortcode = post.get('shortcode')
    post_url = post.get('url')
    post_type = post.get('post_type')
    caption = post.get('caption', '')
    media_urls = post.get('media_urls', [])

    print(f"\n✅ Downloading: {shortcode}")
    print(f"   Type: {post_type}")
    print(f"   Caption: {caption[:100]}...")
    print(f"   URL: {post_url}")

    # پوشه دانلود
    download_dir = Path("instagram_downloads") / shortcode
    download_dir.mkdir(parents=True, exist_ok=True)
    
    # استراتژی دانلود هوشمند
    downloaded = False

    # 1. تلاش با yt-dlp (برای ویدیوها و حتی عکس‌ها)
    ytdlp_output = download_dir / f"{shortcode}_ytdlp.mp4"
    if download_with_ytdlp(post_url, str(ytdlp_output)):
        downloaded = True
        # در صورت موفقیت، اطلاعات پست را ذخیره کن
        with open(download_dir / "info.txt", 'w', encoding='utf-8') as f:
            f.write(f"Download Method: yt-dlp\n")
            f.write(f"Shortcode: {shortcode}\nURL: {post_url}\nCaption: {caption}\n")
    else:
        # 2. اگر yt-dlp موفق نبود، از media_urls استفاده کن
        if media_urls:
            if download_from_media_urls(media_urls, download_dir, shortcode, post_type):
                downloaded = True
                with open(download_dir / "info.txt", 'w', encoding='utf-8') as f:
                    f.write(f"Download Method: media_urls (Apify)\n")
                    f.write(f"Shortcode: {shortcode}\nURL: {post_url}\nCaption: {caption}\n")
        else:
            # 3. هیچ روشی جواب نداد
            print("❌ All download methods failed. No media_urls found and yt-dlp failed.")
            with open(download_dir / "error.txt", 'w', encoding='utf-8') as f:
                f.write(f"Failed to download {shortcode}\nURL: {post_url}\nCaption: {caption}\n")
            sys.exit(1)

    if downloaded:
        print(f"\n🎉 Download completed successfully!")
    else:
        print(f"\n❌ Download failed.")
        sys.exit(1)

if __name__ == '__main__':
    main()
