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
    timeout_seconds: int = 2100
    download_quiet_seconds: int = 20
    scroll_direction: str = 'up'   # ← این خط جدید
    save_screenshots: bool = True
def load_config(path: str = "config.yaml") -> Config:
    """بارگذاری تنظیمات از فایل YAML"""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"❌ فایل تنظیمات {path} یافت نشد!")

    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    # اعتبارسنجی
    if not data.get('channel') and not data.get('start_link'):
        raise ValueError("❌ یا نام کانال (channel) یا لینک شروع (start_link) باید در config.yaml تنظیم شود.")
    if data.get('limit', 0) <= 0:
        raise ValueError("❌ limit باید بزرگ‌تر از صفر باشد.")
    if data.get('max_media_mb', 0) <= 0:
        raise ValueError("❌ max_media_mb باید بزرگ‌تر از صفر باشد.")
    if not data.get('profile_dir'):
        raise ValueError("❌ پوشهٔ پروفایل (profile_dir) مشخص نشده است.")

    # خواندن فیلدهای اختیاری با پیش‌فرض
    timeout_seconds = data.get('timeout_seconds', 2100)
    download_quiet_seconds = data.get('download_quiet_seconds', 20)
    scroll_direction = data.get('scroll_direction', 'up')
    save_screenshots = data.get('save_screenshots', True)    
    if scroll_direction not in ['up', 'down']:
        scroll_direction = 'up'
        
    return Config(
        channel=data['channel'].lstrip('@'),
        limit=data['limit'],
        max_media_mb=data['max_media_mb'],
        output_dir=data.get('output_dir', 'Download'),
        profile_dir=data['profile_dir'],
        delay_between_posts=data.get('delay_between_posts', 1.5),
        channel_name=data.get('channel_name', ''),
        resume=data.get('resume', True),
        start_link=data.get('start_link', ''),
        timeout_seconds=timeout_seconds,
        download_quiet_seconds=download_quiet_seconds,
        scroll_direction=scroll_direction,
        save_screenshots=save_screenshots
    )
