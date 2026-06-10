#!/usr/bin/env python3
import os
import sys
import glob
import urllib.request
import json

def decrypt_gpg(gpg_file, passphrase):
    """Decrypt a GPG file and return content as string."""
    import subprocess
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
    """Return cookie content from cookies[index].txt.gpg (0-based)."""
    files = sorted(glob.glob("cookies*.txt.gpg"))
    if index >= len(files):
        return None, None
    gpg_file = files[index]
    cookie = decrypt_gpg(gpg_file, passphrase)
    if cookie is None:
        return None, gpg_file
    return cookie, gpg_file

def get_public_cookie():
    """Fallback: Get a fresh cookie from public API."""
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

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "next"
    passphrase = os.environ.get("COOKIE_DECRYPT_KEY")
    
    if mode == "public":
        cookie = get_public_cookie()
        if cookie:
            with open("cookies.txt", "w") as f:
                f.write(cookie)
            print("✅ Public cookie saved.")
            return 0
        return 1
    
    elif mode == "next":
        # دریافت آخرین ایندکس استفاده شده (از فایل موقتی)
        last_index_file = ".last_cookie_index"
        if os.path.exists(last_index_file):
            with open(last_index_file, "r") as f:
                last_index = int(f.read().strip())
        else:
            last_index = -1
        
        next_index = last_index + 1
        cookie, gpg_file = get_cookie_by_index(next_index, passphrase)
        if cookie:
            with open("cookies.txt", "w") as f:
                f.write(cookie)
            with open(last_index_file, "w") as f:
                f.write(str(next_index))
            print(f"✅ Using cookie from {gpg_file}")
            return 0
        else:
            # اگر کوکی‌ها تمام شد، از public استفاده کن
            return get_public_cookie_and_save()
    
    return 1

def get_public_cookie_and_save():
    cookie = get_public_cookie()
    if cookie:
        with open("cookies.txt", "w") as f:
            f.write(cookie)
        print("✅ Public cookie saved.")
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(main())
