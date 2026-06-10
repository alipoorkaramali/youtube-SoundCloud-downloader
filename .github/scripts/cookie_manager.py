#!/usr/bin/env python3
import os
import sys
import glob
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
    files = sorted(glob.glob("cookies*.txt.gpg"))
    if index >= len(files):
        return None, None
    gpg_file = files[index]
    cookie = decrypt_gpg(gpg_file, passphrase)
    return cookie, gpg_file

def get_public_cookie():
    print("🔄 Getting cookie from public API...")
    try:
        with urllib.request.urlopen("https://cookies-service.onrender.com/cookies", timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            cookie = data.get("cookie")
            if cookie:
                print("✅ Public cookie obtained.")
                return cookie
    except Exception as e:
        print(f"❌ Public API failed: {e}")
    return None

def save_cookie(content):
    with open("cookies.txt", "w") as f:
        f.write(content)
    print("✅ Cookie saved to cookies.txt")

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "next"
    passphrase = os.environ.get("COOKIE_DECRYPT_KEY")
    if not passphrase:
        print("❌ COOKIE_DECRYPT_KEY environment variable not set.")
        return 1

    if mode == "public":
        cookie = get_public_cookie()
        if cookie:
            save_cookie(cookie)
            return 0
        return 1

    elif mode == "next":
        last_index_file = ".last_cookie_index"
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
            print(f"✅ Using cookie from {gpg_file}")
            return 0
        else:
            # اگر کوکی‌های شخصی تمام شد، به public برگرد
            print("⚠️ No more personal cookies. Falling back to public API.")
            cookie = get_public_cookie()
            if cookie:
                save_cookie(cookie)
                return 0
            return 1

if __name__ == "__main__":
    sys.exit(main())
