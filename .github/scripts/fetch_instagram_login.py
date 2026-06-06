import os
import json
import instaloader
from datetime import datetime

def main():
    username = os.environ.get('TARGET_USERNAME')
    if not username:
        print("❌ TARGET_USERNAME is required")
        exit(1)

    output_file = os.environ.get('OUTPUT_FILE', 'instagram_posts.json')
    login_user = os.environ.get('IG_USERNAME')
    login_pass = os.environ.get('IG_PASSWORD')
    
    if not login_user or not login_pass:
        print("❌ IG_USERNAME or IG_PASSWORD not set")
        exit(1)

    loader = instaloader.Instaloader()
    
    try:
        # لاگین با اعتبار ذخیره شده
        loader.login(login_user, login_pass)
        print("✅ لاگین موفق")
        
        # دریافت پروفایل هدف
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
            'target_username': username,
            'fetched_at': datetime.now().isoformat(),
            'recent_posts': posts
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ موفقیت: {len(posts)} پست برای @{username} دریافت شد.")
        
    except Exception as e:
        print(f"❌ خطا: {e}")
        with open(output_file, 'w') as f:
            json.dump({"error": str(e), "target": username}, f)
        exit(1)

if __name__ == '__main__':
    main()
