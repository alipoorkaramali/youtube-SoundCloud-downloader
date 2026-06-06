import os
import json
import tempfile
import subprocess
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

    # مسیر فایل کوکی رمزگذاری شده (در ریشه مخزن)
    cookie_gpg = "cookies_instagram.txt.gpg"
    if not os.path.exists(cookie_gpg):
        print(f"❌ فایل {cookie_gpg} در ریشه مخزن یافت نشد")
        exit(1)

    # رمزگشایی کوکی در یک فایل موقتی
    cookie_file = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            cookie_file = tmp.name
        
        subprocess.run([
            "gpg", "--batch", "--yes", "--passphrase", cookie_pass,
            "--decrypt", cookie_gpg, "--output", cookie_file
        ], check=True)
        
        # استفاده از instaloader
        import instaloader
        loader = instaloader.Instaloader()
        # بارگذاری session از فایل کوکی (نیاز به نام کاربری دارد، اما مهم نیست)
        # باید نام کاربری با اکانتی که کوکی متعلق به آن است مطابقت داشته باشد.
        # از آنجا که ما کوکی را از یک اکانت معمولی گرفتیم، باید همان نام کاربری را وارد کنیم.
        # برای این کار، از کاربر می‌خواهیم نام کاربری اکانت خودش را به عنوان ورودی بدهد.
        # اما ساده‌تر: می‌توانیم از instaloader با کوکی مستقیم استفاده کنیم.
        # روش صحیح: استفاده از context._session.cookies
        # چون instaloader.load_session_from_file نیاز به فایل session دارد، نه کوکی خام.
        # بنابراین به جای آن از روش جایگزین استفاده می‌کنیم:
        
        # راه حل: نصب instaloader و استفاده از کلاس CookieJar
        import requests
        from http.cookiejar import MozillaCookieJar
        cj = MozillaCookieJar(cookie_file)
        cj.load(ignore_discard=True, ignore_expires=True)
        loader.context._session.cookies.update(cj)
        
        # حالا پروفایل مورد نظر را دریافت می‌کنیم (هر پیج عمومی)
        profile = instaloader.Profile.from_username(loader.context, username)
        posts = []
        for post in profile.get_posts():
            if len(posts) >= 5:
                break
            posts.append({
                'shortcode': post.shortcode,
                'permalink': f"https://www.instagram.com/p/{post.shortcode}/",
                'timestamp': post.date_utc.isoformat(),
                'caption': post.caption if post.caption else '',
                'like_count': post.likes,
                'comment_count': post.comments,
                'media_type': str(post.typename),
                'thumbnail': post.url,
                'video_url': post.video_url if post.is_video else None
            })
        
        result = {
            'username': username,
            'full_name': profile.full_name,
            'follower_count': profile.followers,
            'fetched_at': datetime.now().isoformat(),
            'recent_posts': posts
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ موفقیت: {len(posts)} پست برای @{username} دریافت شد.")
        
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
