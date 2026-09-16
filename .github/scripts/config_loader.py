#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
from pathlib import Path
from dataclasses import dataclass

@dataclass
class Config:
    """تنظیمات پروژه — نسخهٔ مستقل از Apify"""
    channel: str
    limit: int
    max_media_mb: int
    output_dir: str
    profile_dir: str
    delay_between_posts: float
    channel_name: str = ''
    resume: bool = True
    start_link: str = ''
    mega_folder: str = 'TelegramArchive'
    timeout_seconds: int = 2100
    download_quiet_seconds: int = 20
    scroll_direction: str = 'up'
    save_screenshots: bool = True
    retry_failed: bool = False
    only_new_posts: bool = False
    skip_before_id: str = ''
    auto_limit_max: int = 150

def load_config(path: str = "config.yaml") -> Config:
    """بارگذاری تنظیمات از فایل YAML"""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"❌ فایل تنظیمات {path} یافت نشد!")

    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if not data.get('channel') and not data.get('start_link'):
        raise ValueError("❌ یا نام کانال (channel) یا لینک شروع (start_link) باید در config.yaml تنظیم شود.")

    limit = int(data.get('limit', 0) or 0)
    if limit < 0:
        raise ValueError("❌ limit نمی‌تواند منفی باشد (0 = خودکار).")

    # 0 = نامحدود
    max_media_mb = int(data.get('max_media_mb', 0) or 0)
    if max_media_mb < 0:
        raise ValueError("❌ max_media_mb نمی‌تواند منفی باشد (0 = نامحدود).")

    if not data.get('profile_dir'):
        raise ValueError("❌ پوشهٔ پروفایل (profile_dir) مشخص نشده است.")

    timeout_seconds = data.get('timeout_seconds', 2100)
    download_quiet_seconds = data.get('download_quiet_seconds', 20)
    scroll_direction = data.get('scroll_direction', 'up')
    save_screenshots = data.get('save_screenshots', True)
    mega_folder = data.get('mega_folder', 'TelegramArchive')
    retry_failed = data.get('retry_failed', False)
    only_new_posts = data.get('only_new_posts', False)
    skip_before_id = str(data.get('skip_before_id', '') or '').strip()
    auto_limit_max = int(data.get('auto_limit_max', 150) or 150)
    if scroll_direction not in ['up', 'down']:
        scroll_direction = 'up'

    return Config(
        channel=data['channel'].lstrip('@'),
        limit=limit,
        max_media_mb=max_media_mb,
        output_dir=data.get('output_dir', 'Download'),
        profile_dir=data['profile_dir'],
        delay_between_posts=data.get('delay_between_posts', 1.5),
        channel_name=data.get('channel_name', ''),
        resume=data.get('resume', True),
        start_link=data.get('start_link', ''),
        mega_folder=mega_folder,
        timeout_seconds=timeout_seconds,
        download_quiet_seconds=download_quiet_seconds,
        scroll_direction=scroll_direction,
        save_screenshots=save_screenshots,
        retry_failed=retry_failed,
        only_new_posts=only_new_posts,
        skip_before_id=skip_before_id,
        auto_limit_max=auto_limit_max,
    )
