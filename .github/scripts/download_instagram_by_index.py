import os
import sys
import json
import subprocess
from pathlib import Path

def download_post(shortcode):
    """
    دانلود پست اینستاگرام با استفاده از shortcode
    خروجی در پوشه: instagram_downloads/<shortcode>/
    """
    out_dir = Path("instagram_downloads") / shortcode
    out_dir.mkdir(parents=True, exist_ok=True)

    url = f"https://www.instagram.com/p/{shortcode}/"
    
    # اگر فایل کوکی وجود دارد (رمزگشایی شده در workflow)
    cookie_file = Path("cookies.txt")
    cookie_opt = ["--cookies", str(cookie_file)] if cookie_file.exists() else []
    
    # دانلود ویدیو/تصاویر با yt-dlp
    cmd = [
        "yt-dlp",
        "-o", f"{out_dir}/%(title)s.%(ext)s",
        "--write-info-json",
        "--no-overwrites",
        "--no-playlist",
        *cookie_opt,
        url
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ yt-dlp error: {e.stderr}")
        sys.exit(1)
    
    # استخراج نام کاربری از فایل info.json (ساخته شده توسط yt-dlp)
    info_files = list(out_dir.glob("*.info.json"))
    username = "unknown"
    if info_files:
        with open(info_files[0], 'r', encoding='utf-8') as f:
            info = json.load(f)
            username = info.get('uploader', 'unknown')
    
    # ذخیره متادیتا
    meta = {
        "shortcode": shortcode,
        "username": username,
        "download_path": str(out_dir)
    }
    with open(out_dir / "post_info.json", "w") as f:
        json.dump(meta, f, indent=2)
    
    print(f"✅ Downloaded {shortcode} (user: {username})")
    # خروجی برای workflow
    print(f"USERNAME={username}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python download_instagram_by_index.py <shortcode>")
        sys.exit(1)
    shortcode = sys.argv[1]
    download_post(shortcode)
