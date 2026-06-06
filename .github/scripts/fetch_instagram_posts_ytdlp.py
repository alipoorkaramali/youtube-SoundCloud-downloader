import os
import json
import subprocess
import tempfile
import re
from datetime import datetime

def main():
    username = os.environ.get('IG_USERNAME')
    if not username:
        print("❌ IG_USERNAME is required")
        exit(1)

    output_file = os.environ.get('OUTPUT_FILE', 'instagram_posts.json')
    cookie_pass = os.environ.get('INSTAGRAM_COOKIE_PASSPHRASE')
    if not cookie_pass:
        print("❌ INSTAGRAM_COOKIE_PASSPHRASE not set")
        exit(1)

    cookie_gpg = "cookies_instagram.txt.gpg"
    if not os.path.exists(cookie_gpg):
        print(f"❌ فایل {cookie_gpg} در ریشه مخزن یافت نشد")
        exit(1)

    # رمزگشایی کوکی
    cookie_file = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            cookie_file = tmp.name
        
        subprocess.run([
            "gpg", "--batch", "--yes", "--passphrase", cookie_pass,
            "--decrypt", "--output", cookie_file, cookie_gpg
        ], check=True)

        # دریافت لیست پست‌ها با yt-dlp
        profile_url = f"https://www.instagram.com/{username}/"
        cmd = [
            "yt-dlp",
            "--flat-playlist",          # فقط متادیتا، بدون دانلود
            "--dump-json",              # خروجی JSON برای هر ورودی
            "--cookies", cookie_file,
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--no-warnings",
            "--playlist-end", "5",      # فقط ۵ پست آخر
            profile_url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # خروجی شامل چند خط JSON است (هر خط یک پست)
        posts = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            data = json.loads(line)
            # استخراج فیلدهای مورد نیاز
            posts.append({
                'shortcode': data.get('id'),  # یا از 'display_id' استفاده کنید
                'permalink': data.get('webpage_url'),
                'timestamp': datetime.fromtimestamp(data.get('timestamp', 0)).isoformat() if data.get('timestamp') else None,
                'caption': data.get('description', ''),
                'like_count': data.get('like_count', 0),
                'comment_count': data.get('comment_count', 0),
                'media_type': data.get('extractor_key'),  # 'Instagram' 
                'thumbnail': data.get('thumbnail'),
                'video_url': data.get('url') if data.get('url') else None
            })
        
        # اطلاعات پیج (تعداد دنبال‌کننده و نام کامل) از yt-dlp استخراج نمی‌شود.
        # می‌توانیم از یک درخواست ساده برای صفحه اصلی دریافت کنیم، اما فعلاً بی‌نیازیم.
        result_obj = {
            'username': username,
            'full_name': username,  # در صورت نیاز بعداً از HTML استخراج می‌کنیم
            'follower_count': 0,
            'fetched_at': datetime.now().isoformat(),
            'recent_posts': posts
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_obj, f, ensure_ascii=False, indent=2)
        print(f"✅ موفقیت: {len(posts)} پست برای @{username} دریافت شد.")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ خطا在执行 yt-dlp: {e.stderr}")
        with open(output_file, 'w') as f:
            json.dump({"error": str(e.stderr), "username": username}, f)
        exit(1)
    except Exception as e:
        print(f"❌ خطا: {e}")
        with open(output_file, 'w') as f:
            json.dump({"error": str(e), "username": username}, f)
        exit(1)
    finally:
        if cookie_file and os.path.exists(cookie_file):
            os.unlink(cookie_file)

if __name__ == '__main__':
    main()
