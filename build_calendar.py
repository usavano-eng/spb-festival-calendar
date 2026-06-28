#!/usr/bin/env python3
"""
Festival Calendar Builder for St. Petersburg
Automated scraper + HTML generator for geek/anime/roleplay festivals
"""

import json
import csv
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

# ============================================================
# VK API PARSER
# ============================================================
import requests

# List of VK groups to parse (screen names)
# ADD MORE GROUPS HERE - just add a new dict to the list
VK_GROUPS = [
    {"screen_name": "epiccon", "default_themes": ["фантастика", "комиксы", "косплей", "сериалы", "компьютерные игры"]},
    {"screen_name": "aniconspb", "default_themes": ["аниме", "косплей", "японская культура"]},
    {"screen_name": "rurpgfest", "default_themes": ["ролевые игры", "настольные игры", "НРИ"]},
    {"screen_name": "japanfestspb", "default_themes": ["аниме", "японская культура", "субкультуры"]},
    {"screen_name": "toshocon", "default_themes": ["аниме", "японская культура", "косплей"]},
]

VK_API_VERSION = "5.199"
VK_API_URL = "https://api.vk.com/method"

def get_vk_token():
    token = os.environ.get("VK_TOKEN")
    if not token:
        print("WARNING: VK_TOKEN not set. Using sample data only.")
    return token

def resolve_screen_name(token, screen_name):
    try:
        resp = requests.get(
            f"{VK_API_URL}/utils.resolveScreenName",
            params={"screen_name": screen_name, "access_token": token, "v": VK_API_VERSION},
            timeout=10
        )
        data = resp.json()
        if "response" in data and data["response"]:
            return data["response"]["object_id"]
        return None
    except Exception as e:
        print(f"Error resolving {screen_name}: {e}")
        return None

def parse_vk_date(text):
    months_ru = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
        "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
    }

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        year = int(year_match.group(1))
    else:
        year = 2026

    pattern = r"(\d{1,2})[-\u2013\u2014]\s*(\d{1,2})\s+([\u0430-\u044f]+)"
    match = re.search(pattern, text.lower())
    if match:
        day1 = int(match.group(1))
        day2 = int(match.group(2))
        month_name = match.group(3)
        month = months_ru.get(month_name)
        if month:
            date_start = f"{year:04d}-{month:02d}-{day1:02d}"
            date_end = f"{year:04d}-{month:02d}-{day2:02d}"
            return date_start, date_end, True

    pattern_single = r"(\d{1,2})\s+([\u0430-\u044f]+)"
    match = re.search(pattern_single, text.lower())
    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        month = months_ru.get(month_name)
        if month:
            date = f"{year:04d}-{month:02d}-{day:02d}"
            return date, None, True

    return None, None, False

def extract_venue(text):
    venues = ["DAA EXPO", "СКК", "Экспофорум", "Ленэкспо", "Конгресс-холл"]
    for venue in venues:
        if venue.lower() in text.lower():
            return venue
    return "Санкт-Петербург"

def extract_description(text, max_length=200):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if lines:
        desc = lines[0]
        if len(desc) > max_length:
            desc = desc[:max_length] + "..."
        return desc
    return ""

def fetch_vk_posts(token, group_id, count=20):
    try:
        resp = requests.get(
            f"{VK_API_URL}/wall.get",
            params={
                "owner_id": f"-{group_id}",
                "count": count,
                "access_token": token,
                "v": VK_API_VERSION
            },
            timeout=10
        )
        data = resp.json()
        if "response" in data:
            return data["response"]["items"]
        return []
    except Exception as e:
        print(f"Error fetching posts for group {group_id}: {e}")
        return []

def parse_vk_group(token, group_info):
    screen_name = group_info['screen_name']
    default_themes = group_info['default_themes']

    group_id = resolve_screen_name(token, screen_name)
    if not group_id:
        print(f"Could not resolve group: {screen_name}")
        return []

    posts = fetch_vk_posts(token, group_id)
    festivals = []
    today = datetime.now().date()

    for post in posts:
        text = post.get('text', '')
        if not text:
            continue

        lines = [l.strip() for l in text.split('\n') if l.strip()]
        name = lines[0] if lines else f"Event from {screen_name}"
        if len(name) > 80:
            name = name[:80] + '...'

        date_start, date_end, is_confirmed = parse_vk_date(text)
        if not date_start:
            continue

        # FILTER: Skip past events
        try:
            event_date = datetime.strptime(date_start, "%Y-%m-%d").date()
            if event_date < today:
                print(f"  Skipping past event: {name} ({date_start})")
                continue
        except:
            continue

        venue = extract_venue(text)
        description = extract_description(text)

        post_id = post.get('id')
        source_url = f"https://vk.com/{screen_name}?w=wall-{group_id}_{post_id}"

        festival = Festival(
            name=name,
            date_start=date_start,
            date_end=date_end,
            venue=venue,
            city=CITY,
            themes=default_themes.copy(),
            description=description,
            source_url=source_url,
            is_confirmed=is_confirmed
        )
        festivals.append(festival)

    return festivals

def scrape_vk_festivals():
    token = get_vk_token()
    if not token:
        return []

    all_festivals = []
    for group_info in VK_GROUPS:
        print(f"Parsing VK group: {group_info['screen_name']}")
        festivals = parse_vk_group(token, group_info)
        all_festivals.extend(festivals)
        print(f"  Found {len(festivals)} events")

    seen = set()
    unique = []
    for f in all_festivals:
        key = (f.name, f.date_start)
        if key not in seen:
            seen.add(key)
            unique.append(f)

    print(f"Total unique VK festivals: {len(unique)}")
    return unique

# ============================================================
# CONFIGURATION
# ============================================================
CITY = 'Санкт-Петербург'
DATA_FILE = 'festivals_data.json'
HTML_OUTPUT = 'public/index.html'
CSV_OUTPUT = 'public/festivals.csv'

# ============================================================
# DATA STRUCTURE
# ============================================================
class Festival:
    def __init__(self, name, date_start, date_end, venue, city,
                 themes, description, source_url, ticket_url=None,
                 image_url=None, is_confirmed=True):
        self.name = name
        self.date_start = date_start
        self.date_end = date_end
        self.venue = venue
        self.city = city
        self.themes = themes
        self.description = description
        self.source_url = source_url
        self.ticket_url = ticket_url
        self.image_url = image_url
        self.is_confirmed = is_confirmed

    def to_dict(self):
        return {
            'name': self.name,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'venue': self.venue,
            'city': self.city,
            'themes': self.themes,
            'description': self.description,
            'source_url': self.source_url,
            'ticket_url': self.ticket_url,
            'image_url': self.image_url,
            'is_confirmed': self.is_confirmed
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

# ============================================================
# SAMPLE DATA (fallback when VK_TOKEN is not set)
# ============================================================
SAMPLE_FESTIVALS = [
    Festival(
        name='Epic Con',
        date_start='2026-07-11',
        date_end='2026-07-12',
        venue='DAA EXPO',
        city='Санкт-Петербург',
        themes=['фантастика', 'комиксы', 'косплей', 'сериалы', 'компьютерные игры'],
        description='Крупнейший фестиваль поп-культуры. Конкурс косплея, выставочные стенды, Аллея Авторов, настольные и консольные игры, квесты.',
        source_url='https://epiccon.ru/',
        ticket_url='https://epiccon.ru/',
        is_confirmed=True
    ),
    Festival(
        name='АниКон',
        date_start='2026-07-17',
        date_end='2026-07-19',
        venue='Санкт-Петербург',
        city='Санкт-Петербург',
        themes=['аниме', 'косплей', 'японская культура'],
        description='Аниме-фестиваль с сильной сценической программой и косплей-дефиле.',
        source_url='https://vk.com/aniconspb',
        is_confirmed=True
    ),
    Festival(
        name='DiceFest IV',
        date_start='2026-07-25',
        date_end='2026-07-26',
        venue='Санкт-Петербург',
        city='Санкт-Петербург',
        themes=['ролевые игры', 'настольные игры', 'НРИ'],
        description='Фестиваль настольных ролевых игр. Игротеки, мастер-классы, новые знакомства.',
        source_url='https://taplink.cc/rurpgfest',
        is_confirmed=True
    ),
    Festival(
        name='ДАНЖН ФЕСТ',
        date_start='2026-08-01',
        date_end='2026-08-02',
        venue='Санкт-Петербург',
        city='Санкт-Петербург',
        themes=['ролевые игры', 'фэнтези', 'НРИ'],
        description='Фестиваль настольных ролевых игр в жанре dungeon crawl.',
        source_url='https://taplink.cc/rurpgfest',
        is_confirmed=True
    ),
    Festival(
        name='Япония.Фест',
        date_start='2026-05-22',
        date_end='2026-09-06',
        venue='Санкт-Петербург',
        city='Санкт-Петербург',
        themes=['аниме', 'японская культура', 'субкультуры'],
        description='Долгосрочная выставочная программа японской культуры.',
        source_url='https://vk.com/japanfestspb',
        is_confirmed=True
    ),
    Festival(
        name='ToshoCon',
        date_start='2026-09-15',
        date_end='2026-09-17',
        venue='Санкт-Петербург',
        city='Санкт-Петербург',
        themes=['аниме', 'японская культура', 'косплей'],
        description='Крупный аниме-фестиваль с упором на японскую культуру. Точные даты уточняются.',
        source_url='https://vk.com/toshocon',
        is_confirmed=False
    ),
]
