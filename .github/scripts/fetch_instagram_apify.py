import os
import json
from apify_client import ApifyClient
from datetime import datetime

def main():
    username = os.environ.get('TARGET_USERNAME')
    post_count_str = os.environ.get('POST_COUNT', '5')
    output_file = os.environ.get('OUTPUT_FILE', 'instagram_posts.json')
    api_token = os.environ.get('APIFY_API_TOKEN')

    if not username or not api_token:
        print("❌ Missing TARGET_USERNAME or APIFY_API_TOKEN")
        exit(1)

    try:
        post_count = int(post_count_str)
        if post_count not in [5, 10, 15, 20]:
            post_count = 5
    except:
        post_count = 5

    print(f"🔍 Fetching {post_count} posts from @{username}...")
    client = ApifyClient(api_token)
    actor_id = "khadinakbar/instagram-posts-scraper"   # اقتصادی

    run_input = {
        "instagramUsernames": [username],
        "maxPostsPerTarget": post_count,
        "includeRecentComments": True,
        "proxyConfiguration": { "useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"] }
    }

    run = client.actor(actor_id).call(run_input=run_input)
    posts = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        posts.append(item)
        if len(posts) >= post_count:
            break

    result = {
        'target_username': username,
        'requested_posts': post_count,
        'fetched_posts': len(posts),
        'fetched_at': datetime.now().isoformat(),
        'recent_posts': posts
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved {len(posts)} posts to {output_file}")

if __name__ == '__main__':
    main()
