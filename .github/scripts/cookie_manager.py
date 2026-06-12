#!/usr/bin/env python3
import os
import sys
import urllib.request
import json
import subprocess

def decrypt_gpg(gpg_file, passphrase):
    try:
        result = subprocess.run(
            ["gpg", "--batch", "--yes", "--decrypt", "--passphrase", passphrase, gpg_file],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except:
        return None

def get_cookie_by_index(index, passphrase):
    base_files = ["config/cookies.txt.gpg", "config/cookies1.txt.gpg", "config/cookies2.txt.gpg", "config/cookies3.txt.gpg"]
    existing_files = [f for f in base_files if os.path.exists(f)]
    if index >= len(existing_files):
        return None, None
    gpg_file = existing_files[index]
    cookie = decrypt_gpg(gpg_file, passphrase)
    return cookie, gpg_file

def test_public_api():
    """آیا API عمومی پاسخ می‌دهد؟"""
    try:
        req = urllib.request.Request(
            "https://cookies-service.onrender.com/cookies",
            headers={"User-Agent": "Mozilla/5.0"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get("cookie") is not None
    except:
        return False

def get_public_cookie():
    print("🌐 دریافت کوکی از API عمومی...")
    try:
        req = urllib.request.Request(
            "https://cookies-service.onrender.com/cookies",
            headers={"User-Agent": "Mozilla/5.0"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            cookie = data.get("cookie")
            if cookie:
                print("✅ کوکی عمومی دریافت شد.")
                return cookie
    except Exception as e:
        print(f"❌ خطا در دریافت کوکی عمومی: {e}")
    return None

def save_cookie(content):
    with open("cookies.txt", "w") as f:
        f.write(content)
    print("✅ کوکی ذخیره شد.")

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "next"
    passphrase = os.environ.get("COOKIE_DECRYPT_KEY")
    if not passphrase:
        print("❌ COOKIE_DECRYPT_KEY environment variable not set.")
        return 1

    if mode == "test_public":
        # فقط تست می‌کند، بدون ذخیره
        if test_public_api():
            print("✅ Public API is reachable and returns a cookie.")
            return 0
        else:
            print("⚠️ Public API is NOT available.")
            return 1

    elif mode == "public":
        cookie = get_public_cookie()
        if cookie:
            save_cookie(cookie)
            return 0
        return 1

    elif mode == "next":
        last_index_file = "State/.last_cookie_index"
        if os.path.exists(last_index_file):
            with open(last_index_file, "r") as f:
                last_index = int(f.read().strip())
        else:
            last_index = -1
        next_index = last_index + 1
        cookie, gpg_file = get_cookie_by_index(next_index, passphrase)
        if cookie:
            save_cookie(cookie)
            with open(last_index_file, "w") as f:
                f.write(str(next_index))
            print(f"✅ استفاده از کوکی شخصی: {gpg_file}")
            return 0
        else:
            print("⚠️ هیچ کوکی شخصی دیگری موجود نیست. تلاش برای کوکی عمومی...")
            cookie = get_public_cookie()
            if cookie:
                save_cookie(cookie)
                return 0
            return 1

if __name__ == "__main__":
    sys.exit(main())
