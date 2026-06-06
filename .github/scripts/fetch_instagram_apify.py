import os
import json
from apify_client import ApifyClient
from datetime import datetime

def main():
    # دریافت ورودی‌ها از متغیرهای محیطی
    username = os.environ.get('TARGET_USERNAME')
    post_count_str = os.environ.get('POST_COUNT', '5')
    output_file = os.environ.get('OUTPUT_FILE', 'instagram_posts.json')
    api_token = os.environ.get('APIFY_API_TOKEN')

    if not username:
        print("❌ TARGET_USERNAME is required")
        exit(1)
    if not api_token:
        print("❌ APIFY_API_TOKEN not set in secrets")
        exit(1)

    # تبدیل به عدد صحیح
    try:
        post_count = int(post_count_str)
    except ValueError:
        print("⚠️ تعداد پست نامعتبر، استفاده از مقدار پیش‌فرض 5")
        post_count = 5

    # اطمینان از اینکه عدد در محدوده مجاز است (فقط برای ایمنی)
    if post_count not in [5, 10, 15, 20]:
        print(f"⚠️ تعداد پست {post_count} مجاز نیست. نزدیک‌ترین مقدار مجاز (5) استفاده می‌شود.")
        post_count = 5

    print(f"🔍 در حال دریافت {post_count} پست آخر از @{username}...")

    try:
        client = ApifyClient(api_token)
        actor_id = "khadinakbar/instagram-posts-scraper"

        run_input = {
            "instagramUsernames": [username],
            "maxPostsPerTarget": post_count,
            "includeRecentComments": True,
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"]
            }
        }

        print(f"🚀 اجرای Actor: {actor_id}")
        run = client.actor(actor_id).call(run_input=run_input)
        print(f"✅ اجرا موفق. شناسه Run: {run['id']}")

        # دریافت تمام آیتم‌ها (هر آیتم یک پست کامل است)
        posts = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            posts.append(item)   # کل آیتم را بدون هیچ فیلتری ذخیره کن
            if len(posts) >= post_count:
                break

        # ساختار خروجی نهایی
        result = {
            'target_username': username,
            'requested_posts': post_count,
            'fetched_posts': len(posts),
            'fetched_at': datetime.now().isoformat(),
            'recent_posts': posts   # هر پست شامل تمام فیلدهای اصلی اکتور است
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"🎉 موفقیت: {len(posts)} پست از @{username} دریافت شد.")
        print(f"📄 خروجی در فایل {output_file} ذخیره گردید.")

    except Exception as e:
        print(f"❌ خطا: {str(e)}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({"error": str(e), "target": username, "requested": post_count}, f)
        exit(1)

if __name__ == '__main__':
    main()
