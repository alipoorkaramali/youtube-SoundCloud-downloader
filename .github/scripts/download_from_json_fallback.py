#!/usr/bin/env python3
# .github/scripts/download_from_json_fallback.py
import os
import sys
import json
import glob
import subprocess
import requests
from pathlib import Path

def find_json_for_shortcode(shortcode):
    """جستجو在所有 فایل‌های JSON داخل instagram_data برای shortcode مورد نظر"""
    json_files = glob.glob("instagram_data/*.json")
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            continue

        # ساختارهای مختلف JSON خروجی Apify یا سایر crawlerها را پوشش می‌دهد
        # حالت اول: لیست مستقیم از پست‌ها
        if isinstance(data, list):
            for post in data:
                if isinstance(post, dict) and post.get("shortcode") == shortcode:
                    return post, jf
        # حالت دوم: دیکشنری با کلیدهای احتمالی حاوی لیست پست‌ها
        elif isinstance(data, dict):
            # کلیدهای رایج
            for key in ["posts", "items", "data", "graphql", "post"]:
                if key in data and isinstance(data[key], list):
                    for post in data[key]:
                        if isinstance(post, dict) and post.get("shortcode") == shortcode:
                            return post, jf
            # خود دیکشنری ممکن است خودش یک پست باشد
            if data.get("shortcode") == shortcode:
                return data, jf
    return None, None

def download_file(url, output_path):
    """دانلود فایل با requests (stream)"""
    try:
        r = requests.get(url, stream=True, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"⚠️ دانلود مستقیم ناموفق: {e}")
        return False

def download_with_ytdlp(shortcode, output_dir, cookies_file=None):
    """اجرای yt-dlp برای دانلود کل پست (عکس/ویدیو/کاروسل)"""
    url = f"https://www.instagram.com/p/{shortcode}/"
    cmd = ["yt-dlp", "-o", f"{output_dir}/%(title)s.%(ext)s", url]
    if cookies_file and Path(cookies_file).exists():
        cmd.extend(["--cookies", cookies_file])
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ yt-dlp خطا: {e.stderr}")
        return False

def extract_media_urls(obj):
    """بازگشتی لینک‌های cdninstagram یا fbcdn را از هر شیء JSON استخراج می‌کند"""
    urls = []
    if isinstance(obj, dict):
        # لینک‌های مستقیم شناخته شده
        if "display_url" in obj and obj["display_url"]:
            urls.append(obj["display_url"])
        if "video_url" in obj and obj["video_url"]:
            urls.append(obj["video_url"])
        # carousel (چند رسانه‌ای)
        if "edge_sidecar_to_children" in obj:
            edges = obj["edge_sidecar_to_children"].get("edges", [])
            for edge in edges:
                node = edge.get("node", {})
                if "display_url" in node:
                    urls.append(node["display_url"])
                if "video_url" in node:
                    urls.append(node["video_url"])
        # جستجوی بازگشتی در تمام مقادیر
        for v in obj.values():
            urls.extend(extract_media_urls(v))
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(extract_media_urls(item))
    elif isinstance(obj, str):
        # فیلتر لینک‌های رسانه
        if "cdninstagram.com" in obj or "fbcdn.net" in obj:
            urls.append(obj)
    return urls

def main():
    if len(sys.argv) < 2:
        print("❌ استفاده: python download_from_json_fallback.py <shortcode>")
        sys.exit(1)

    shortcode = sys.argv[1]
    base_dir = Path("instagram_downloads") / shortcode
    base_dir.mkdir(parents=True, exist_ok=True)

    # ---------- مرحله ۱: جستجو در instagram_data ----------
    post_data, source_file = find_json_for_shortcode(shortcode)
    if not post_data:
        print(f"⚠️ shortcode {shortcode} در هیچ فایل JSON داخل instagram_data یافت نشد. رفتن به yt-dlp...")
    else:
        print(f"📄 پست در فایل {source_file} پیدا شد.")
        # استخراج لینک‌های مستقیم
        urls = extract_media_urls(post_data)
        urls = list(set(urls))  # حذف تکراری
        print(f"🔍 {len(urls)} لینک مستقیم استخراج شد.")

        # دانلود با requests
        success = False
        for i, url in enumerate(urls):
            # تشخیص پسوند از URL (پس از حذف query string)
            base_url = url.split("?")[0]
            ext = base_url.split(".")[-1].lower()
            if ext not in ["jpg", "jpeg", "png", "mp4", "mov", "gif"]:
                ext = "mp4" if "video" in url else "jpg"
            filename = f"media_{i+1}.{ext}"
            out_path = base_dir / filename
            if download_file(url, out_path):
                print(f"✅ دانلود مستقیم: {filename}")
                success = True
            else:
                print(f"❌ شکست در دانلود مستقیم: {url[:100]}...")

        if success:
            print("🎉 همه فایل‌های قابل دانلود با روش مستقیم دریافت شدند.")
            # ذخیره post_info.json برای خواندن username بعداً
            # نام کاربری را از post_data استخراج می‌کنیم
            username = None
            if "owner" in post_data and isinstance(post_data["owner"], dict):
                username = post_data["owner"].get("username")
            if not username:
                username = post_data.get("username")
            if not username:
                username = "unknown"
            with open(base_dir / "post_info.json", "w", encoding="utf-8") as f:
                json.dump({"shortcode": shortcode, "username": username}, f)
            return  # موفقیت، پایان کار

        print("⚠️ هیچ لینک مستقیمی کار نکرد. رفتن به مرحله yt-dlp...")

    # ---------- مرحله ۲: yt-dlp بدون کوکی ----------
    print("🔄 تلاش با yt-dlp (بدون کوکی)...")
    if download_with_ytdlp(shortcode, base_dir):
        print("✅ دانلود با yt-dlp بدون کوکی موفقیت‌آمیز بود.")
        # استخراج نام کاربری از خروجی yt-dlp (اجرای دوباره --dump-json)
        try:
            result = subprocess.run(["yt-dlp", "--dump-json", f"https://www.instagram.com/p/{shortcode}/"],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                info = json.loads(result.stdout)
                username = info.get("uploader", "unknown")
                with open(base_dir / "post_info.json", "w", encoding="utf-8") as f:
                    json.dump({"shortcode": shortcode, "username": username}, f)
        except:
            with open(base_dir / "post_info.json", "w", encoding="utf-8") as f:
                json.dump({"shortcode": shortcode, "username": "unknown"}, f)
        return

    # ---------- مرحله ۳: yt-dlp با کوکی ----------
    cookies_path = os.environ.get("INSTAGRAM_COOKIES_PATH")
    if cookies_path and Path(cookies_path).exists():
        print("🍪 تلاش با yt-dlp + کوکی...")
        if download_with_ytdlp(shortcode, base_dir, cookies_path):
            print("✅ دانلود با کوکی موفقیت‌آمیز بود.")
            # مثل بالا سعی در استخراج username
            try:
                result = subprocess.run(["yt-dlp", "--dump-json", f"https://www.instagram.com/p/{shortcode}/", "--cookies", cookies_path],
                                        capture_output=True, text=True)
                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    username = info.get("uploader", "unknown")
                    with open(base_dir / "post_info.json", "w", encoding="utf-8") as f:
                        json.dump({"shortcode": shortcode, "username": username}, f)
            except:
                with open(base_dir / "post_info.json", "w", encoding="utf-8") as f:
                    json.dump({"shortcode": shortcode, "username": "unknown"}, f)
            return
        else:
            print("❌ حتی با کوکی هم دانلود نشد.")
    else:
        print("⚠️ فایل کوکی در دسترس نیست.")

    print("💥 دانلود با هیچ روشی انجام نشد.")
    sys.exit(1)

if __name__ == "__main__":
    main()
