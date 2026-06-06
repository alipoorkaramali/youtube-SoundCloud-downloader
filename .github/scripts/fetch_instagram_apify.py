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

    print(f"🔍 در حال دریافت آخرین پست‌های @{username} از طریق Apify...")

    try:
        # راه‌اندازی کلاینت Apify
        client = ApifyClient(api_token)

        # تعیین Actor ورودی (Instagram Scraper با قیمت اقتصادی)
        run_input = {
            "usernames": [username],
            "resultsPerPage": 5,  # فقط ۵ پست آخر
            "proxyConfiguration": { "useApifyProxy": True }
        }

        # اجرای Actor (اینجا از Actor ارزان‌قیمت پیش‌فرض استفاده شده)
        actor_id = "muhammetakkurtt/instagram-scraper"  # قیمت: $1.00 / 1,000
        print(f"🚀 در حال اجرای Actor با شناسه: {actor_id} ...")

        # فراخوانی Actor و انتظار برای اتمام
        run = client.actor(actor_id).call(run_input=run_input)
        print(f"✅ Actor با موفقیت اجرا شد. شناسه Run: {run['id']}")

        # دریافت نتایج از Dataset Actor
        posts = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            # داده‌های هر پست را بر اساس نیازتان ساختاردهی کنید
            post_data = {
                'shortcode': item.get('shortcode'),
                'permalink': item.get('url'),
                'timestamp': item.get('timestamp'),
                'caption': item.get('caption'),
                'like_count': item.get('likesCount'),
                'comment_count': item.get('commentsCount'),
                'media_type': item.get('type'),
                'thumbnail': item.get('displayUrl'),
                'video_url': item.get('videoUrl')
            }
            posts.append(post_data)
            if len(posts) >= 5:  # اطمینان از حداکثر ۵ پست
                break

        # ساختار خروجی نهایی
        result = {
            'target_username': username,
            'fetched_at': datetime.now().isoformat(),
            'recent_posts': posts[:5]
        }

        # ذخیره خروجی در فایل JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"🎉 موفقیت: {len(posts)} پست برای @{username} دریافت و در {output_file} ذخیره شد.")

    except Exception as e:
        print(f"❌ خطای پیش‌بینی‌نشده: {str(e)}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({"error": str(e), "target": username}, f)
        exit(1)

if __name__ == '__main__':
    main()
