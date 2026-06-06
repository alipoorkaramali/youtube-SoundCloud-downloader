import os
import json
from apify_client import ApifyClient
from datetime import datetime

def main():
    # دریافت ورودی‌ها از متغیرهای محیطی
    username = os.environ.get('TARGET_USERNAME')
    output_file = os.environ.get('OUTPUT_FILE', 'instagram_posts.json')
    api_token = os.environ.get('APIFY_API_TOKEN')

    if not username:
        print("❌ TARGET_USERNAME is required")
        exit(1)
    if not api_token:
        print("❌ APIFY_API_TOKEN not set in secrets")
        exit(1)

    print(f"🔍 در حال دریافت آخرین ۵ پست از @{username} با اکتور پیشرفته...")

    try:
        # راه‌اندازی کلاینت Apify
        client = ApifyClient(api_token)

        # شناسه اکتور تخصصی اینستاگرام (کامل و بهینه)
        actor_id = "khadinakbar/instagram-posts-scraper"
        
        # ورودی دقیق برای گرفتن فقط ۵ پست با حداکثر اطلاعات
        run_input = {
            "instagramUsernames": [username],
            "maxPostsPerTarget": 5,                # دقیقاً ۵ پست
            "includeRecentComments": True,         # دریافت کامنت‌های اخیر
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"]  # پروکسی مسکونی برای جلوگیری از بلاک
            }
        }

        print(f"🚀 اجرای Actor: {actor_id}")
        run = client.actor(actor_id).call(run_input=run_input)
        print(f"✅ اجرا موفق. شناسه Run: {run['id']}")

        # دریافت نتایج از Dataset
        posts = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            # استخراج فیلدهای مورد نیاز (اکتور خروجی غنی دارد)
            post = {
                'shortcode': item.get('shortcode'),
                'permalink': item.get('url') or f"https://www.instagram.com/p/{item.get('shortcode')}/",
                'timestamp': item.get('timestamp'),
                'caption': item.get('caption'),
                'like_count': item.get('likesCount'),
                'comment_count': item.get('commentsCount'),
                'media_type': item.get('mediaType'),  # 'Image', 'Video', 'Carousel'
                'thumbnail': item.get('displayUrl'),
                'video_url': item.get('videoUrl') if item.get('mediaType') == 'Video' else None
            }
            posts.append(post)
            # فقط ۵ پست اول را نگه می‌داریم (امنیت بیشتر)
            if len(posts) >= 5:
                break

        # ساختار خروجی نهایی
        result = {
            'target_username': username,
            'fetched_at': datetime.now().isoformat(),
            'recent_posts': posts[:5]
        }

        # ذخیره در فایل JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"🎉 موفقیت: {len(posts)} پست برای @{username} دریافت شد.")
        print(f"📄 خروجی در فایل {output_file} ذخیره گردید.")

    except Exception as e:
        print(f"❌ خطا: {str(e)}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({"error": str(e), "target": username}, f)
        exit(1)

if __name__ == '__main__':
    main()
