#!/usr/bin/env python3
import os
import sys
import glob
import random
import subprocess
import urllib.request
import json

COOKIE_DIR = "."
OUTPUT_COOKIE = "cookies.txt"

def decrypt_gpg(gpg_file, passphrase):
    """Decrypt a GPG file and return the content as string."""
    try:
        result = subprocess.run(
            ["gpg", "--batch", "--yes", "--decrypt", "--passphrase", passphrase, gpg_file],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None

def validate_cookie(cookie_content):
    """Check if cookie works by making a test request to YouTube."""
    if not cookie_content:
        return False
    try:
        # ایجاد یک درخواست تست ساده با کوکی
        req = urllib.request.Request(
            "https://www.youtube.com/youtubei/v1/player?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Cookie": cookie_content.strip()
            }
        )
        # ارسال یک درخواست ساده JSON
        data = json.dumps({"videoId": "dQw4w9WgXcQ"}).encode('utf-8')
        with urllib.request.urlopen(req, data=data, timeout=10) as response:
            return response.getcode() == 200
    except Exception:
        return False

def get_public_cookie():
    """Fallback: Get a fresh cookie from public API."""
    print("🔄 Attempting to get cookie from public API...")
    try:
        with urllib.request.urlopen("https://cookies-service.onrender.com/cookies", timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            cookie = data.get("cookie")
            if cookie:
                print("✅ Successfully obtained public cookie.")
                return cookie
    except Exception as e:
        print(f"❌ Public API failed: {e}")
    return None

def main():
    # مرحله 1: جستجوی فایل‌های GPG کوکی
    cookie_files = glob.glob("cookies*.txt.gpg")
    if not cookie_files:
        print("⚠️ No encrypted cookie files found. Falling back to public API.")
        fallback_cookie = get_public_cookie()
        if fallback_cookie:
            with open(OUTPUT_COOKIE, "w") as f:
                f.write(fallback_cookie)
            print(f"✅ Public cookie saved to {OUTPUT_COOKIE}")
            return 0
        else:
            print("❌ No cookie source available.")
            return 1

    # مرحله 2: دریافت رمز از secrets (از طریق متغیر محیطی)
    passphrase = os.environ.get("COOKIE_DECRYPT_KEY")
    if not passphrase:
        print("❌ COOKIE_DECRYPT_KEY environment variable not set.")
        return 1

    # مرحله 3: چرخش تصادفی و تست کوکی‌ها
    random.shuffle(cookie_files)
    for gpg_file in cookie_files:
        print(f"🎲 Trying cookie from: {gpg_file}")
        cookie_content = decrypt_gpg(gpg_file, passphrase)
        if not cookie_content:
            print(f"⚠️ Failed to decrypt {gpg_file}")
            continue
        
        if validate_cookie(cookie_content):
            print(f"✅ Valid cookie found in {gpg_file}")
            with open(OUTPUT_COOKIE, "w") as f:
                f.write(cookie_content)
            return 0
        else:
            print(f"❌ Invalid cookie in {gpg_file}")

    # مرحله 4: اگر همه کوکی‌ها نامعتبر بودند، از API عمومی استفاده کن
    print("⚠️ All local cookies are invalid. Using public API as fallback.")
    fallback_cookie = get_public_cookie()
    if fallback_cookie:
        with open(OUTPUT_COOKIE, "w") as f:
            f.write(fallback_cookie)
        print(f"✅ Public cookie saved to {OUTPUT_COOKIE}")
        return 0
    else:
        print("❌ All cookie sources exhausted. Download may fail.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
