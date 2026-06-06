import os
import json
import tempfile
import subprocess
from datetime import datetime
import instaloader
from http.cookiejar import MozillaCookieJar

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

    cookie_file = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            cookie_file = tmp.name
        
        subprocess.run([
            "gpg", "--batch", "--yes", "--passphrase", cookie_pass,
            "--decrypt", "--output", cookie_file, cookie_gpg
        ], check=True)

        # ایجاد loader با User-Agent
        loader = instaloader.Instaloader()
        loader.context._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # بارگذاری کوکی
        cj = MozillaCookieJar(cookie_file)
        cj.load(ignore_discard=True, ignore_expires=True)
        loader.context._session.cookies.update(cj)
        
        # دریافت پروفایل
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
