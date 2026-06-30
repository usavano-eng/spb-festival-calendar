#!/usr/bin/env python3
# Generated: 2026-06-30 23:02:00 MSK
# Festival Calendar Builder for St. Petersburg
# Automated scraper + HTML generator for geek/anime/roleplay festivals

import json
import csv
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from string import Template

import requests

# Timezone for all timestamps
MSK = timezone(timedelta(hours=3))

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
    """Extract date range from VK post text. Returns (start, end, is_confirmed, has_explicit_year)."""
    months_ru = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
        "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
    }

    # Check for explicit year in text
    year_match = re.search(r"\b(20\d{2})\b", text)
    explicit_year = year_match is not None
    year = int(year_match.group(1)) if year_match else datetime.now(MSK).year

    text_lower = text.lower()

    # Pattern 1: Range with dash/en-dash/em-dash: "11-12 июля"
    pattern_range = r"(\d{1,2})[-\u2013\u2014]\s*(\d{1,2})\s+([\u0430-\u044f]+)"
    match = re.search(pattern_range, text_lower)
    if match:
        day1, day2, month_name = int(match.group(1)), int(match.group(2)), match.group(3)
        month = months_ru.get(month_name)
        if month:
            return f"{year:04d}-{month:02d}-{day1:02d}", f"{year:04d}-{month:02d}-{day2:02d}", True, explicit_year

    # Pattern 2: Range with "и": "11 и 12 июля"
    pattern_and = r"(\d{1,2})\s+и\s+(\d{1,2})\s+([\u0430-\u044f]+)"
    match = re.search(pattern_and, text_lower)
    if match:
        day1, day2, month_name = int(match.group(1)), int(match.group(2)), match.group(3)
        month = months_ru.get(month_name)
        if month:
            return f"{year:04d}-{month:02d}-{day1:02d}", f"{year:04d}-{month:02d}-{day2:02d}", True, explicit_year

    # Pattern 3: Single date: "11 июля"
    pattern_single = r"(\d{1,2})\s+([\u0430-\u044f]+)"
    match = re.search(pattern_single, text_lower)
    if match:
        day, month_name = int(match.group(1)), match.group(2)
        month = months_ru.get(month_name)
        if month:
            return f"{year:04d}-{month:02d}-{day:02d}", None, True, explicit_year

    return None, None, False, False

def extract_venue(text):
    venues = ["DAA EXPO", "СКК", "Экспофорум", "Ленэкспо", "Конгресс-холл", "Севкабель Порт"]
    for venue in venues:
        if venue.lower() in text.lower():
            return venue
    return "Санкт-Петербург"

def extract_description(text, max_length=400):
    """Extract first meaningful line as description."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if lines:
        for line in lines[1:] if len(lines) > 1 else lines:
            if len(line) > 20:
                desc = line
                break
        else:
            desc = lines[0]
        return desc[:max_length] + "..." if len(desc) > max_length else desc
    return ""

def fetch_vk_posts(token, group_id, count=20):
    try:
        resp = requests.get(
            f"{VK_API_URL}/wall.get",
            params={"owner_id": f"-{group_id}", "count": count, "access_token": token, "v": VK_API_VERSION},
            timeout=10
        )
        data = resp.json()
        return data["response"]["items"] if "response" in data else []
    except Exception as e:
        print(f"Error fetching posts for group {group_id}: {e}")
        return []

def parse_vk_group(token, group_info):
    screen_name = group_info["screen_name"]
    default_themes = group_info["default_themes"]
    group_id = resolve_screen_name(token, screen_name)
    if not group_id:
        print(f"Could not resolve group: {screen_name}")
        return []
    posts = fetch_vk_posts(token, group_id)
    festivals = []
    today = datetime.now(MSK).date()
    max_future = today + timedelta(days=550)

    for post in posts:
        text = post.get("text", "")
        if not text:
            continue

        post_date_ts = post.get("date")
        post_date = datetime.fromtimestamp(post_date_ts).date() if post_date_ts else today
        post_age_days = (today - post_date).days

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        name = lines[0] if lines else f"Event from {screen_name}"

        date_start, date_end, is_confirmed, explicit_year = parse_vk_date(text)
        if not date_start:
            continue

        try:
            event_date = datetime.strptime(date_start, "%Y-%m-%d").date()
        except:
            continue

        # CHECK 1: Skip past events
        if event_date < today:
            print(f"  Skipping past event: {name} ({date_start})")
            continue

        # CHECK 2: Skip events too far in the future
        if event_date > max_future:
            print(f"  Skipping too-far-future event: {name} ({date_start})")
            continue

        # CHECK 3: Old post without explicit year
        if post_age_days > 90 and not explicit_year:
            print(f"  Skipping old post without explicit year: {name}")
            continue

        # CHECK 4: Suspicious cross-year post
        if not explicit_year and post_date.year < today.year and event_date.year == today.year:
            print(f"  Skipping suspicious cross-year post: {name}")
            continue

        # CHECK 5: Skip promotional posts
        promo_keywords = [
            "повышение цен", "подорожание", "скидка", "акция", "распродажа",
            "купить билет", "заявки", "прием заявок", "конкурс", "отбор",
            "последний день", "успейте", "поторопитесь", "один месяц",
            "представляем партнера", "официальный партнер", "дорогие друзья"
        ]
        is_promo = any(kw in text.lower() for kw in promo_keywords)

        # Count how many dates are in the text - promo posts usually mention only one date
        date_mentions = len(re.findall(r"\d{1,2}\s+[\u0430-\u044f]+", text.lower()))

        # Skip if clearly promotional: has promo keywords AND is short OR has only one date mention
        if is_promo and (len(text) < 200 or date_mentions < 2):
            print(f"  Skipping promotional post: {name[:60]}...")
            continue

        venue = extract_venue(text)
        description = extract_description(text)
        post_id = post.get("id")
        source_url = f"https://vk.com/{screen_name}?w=wall-{group_id}_{post_id}"

        is_confirmed = explicit_year or (date_end is not None)

        festivals.append(Festival(
            name=name, date_start=date_start, date_end=date_end, venue=venue,
            city=CITY, themes=default_themes.copy(), description=description,
            source_url=source_url, is_confirmed=is_confirmed
        ))
    return festivals


def normalize_event_name(name):
    """Extract core event name for deduplication."""
    cleaned = re.sub(r"\[club\d+\|[^\]]+\]", "", name)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()

    # Known event patterns - exact matches for core names
    event_patterns = [
        (r"\bepic\s*con\b", "epiccon"),
        (r"\banicon\b", "anicon"),
        (r"\bdice\s*fest\b", "dicefest"),
        (r"\bданжн\s*фест\b", "danjnfest"),
        (r"\btoshocon\b", "toshocon"),
        (r"\bjapan\s*fest\b", "japanfest"),
        (r"\bяпония\.?\s*фест\b", "japanfest"),
        (r"\bролевой\s*маяк\b", "rolemayak"),
    ]

    for pattern, core_name in event_patterns:
        if re.search(pattern, cleaned):
            return core_name

    # Fallback: extract significant words
    words = cleaned.split()
    significant = [w for w in words if len(w) > 3 and w not in
                   ["фестиваль", "событие", "мероприятие", "санкт", "петербург", "проведет", "пройдет", "года", "июля", "августа", "сентября"]]
    return " ".join(significant[:3]) if significant else cleaned[:30]


def normalize_date_for_dedup(date_start, date_end):
    """Normalize date for deduplication: always return (start, end) where end may equal start."""
    if date_end is None:
        return date_start, date_start
    return date_start, date_end


def deduplicate_festivals(festivals):
    """Deduplicate by normalized name + normalized date range. 
    Keep the entry with:
    - longest description
    - explicit date_end if available
    - explicit year if available
    - latest post (most recent update)
    """
    groups = {}

    for f in festivals:
        norm_name = normalize_event_name(f.name)
        norm_start, norm_end = normalize_date_for_dedup(f.date_start, f.date_end)
        # Use month-level key for deduplication: same event in same month = duplicate
        month_key = norm_start[:7]  # YYYY-MM
        key = (norm_name, month_key)

        if key not in groups:
            groups[key] = []
        groups[key].append(f)

    result = []
    for key, group in groups.items():
        # Scoring: prefer entries with more info
        def score(f):
            s = len(f.description)  # longer description = better
            s += 100 if f.date_end else 0  # prefer entries with end date
            s += 100 if f.is_confirmed else 0  # prefer confirmed dates
            return s

        best = max(group, key=score)

        # Merge date_end from other entries if best doesn't have it
        if not best.date_end:
            for other in group:
                if other.date_end and other.date_start == best.date_start:
                    best.date_end = other.date_end
                    best.is_confirmed = True
                    break

        result.append(best)

    return result


def scrape_vk_festivals():
    token = get_vk_token()
    if not token:
        return [], "VK API недоступен"
    all_festivals = []
    for group_info in VK_GROUPS:
        print(f"Parsing VK group: {group_info['screen_name']}")
        festivals = parse_vk_group(token, group_info)
        all_festivals.extend(festivals)
        print(f"  Found {len(festivals)} events")

    unique = deduplicate_festivals(all_festivals)
    print(f"Total after deduplication: {len(unique)} (was {len(all_festivals)})")
    return unique, datetime.now(MSK).strftime("%d %B %Y, %H:%M")

CITY = "Санкт-Петербург"
DATA_FILE = "festivals_data.json"
HTML_OUTPUT = "public/index.html"
CSV_OUTPUT = "public/festivals.csv"

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
            "name": self.name, "date_start": self.date_start, "date_end": self.date_end,
            "venue": self.venue, "city": self.city, "themes": self.themes,
            "description": self.description, "source_url": self.source_url,
            "ticket_url": self.ticket_url, "image_url": self.image_url,
            "is_confirmed": self.is_confirmed
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

SAMPLE_FESTIVALS = [
    Festival(name="Epic Con", date_start="2026-07-11", date_end="2026-07-12", venue="Севкабель Порт",
             city="Санкт-Петербург", themes=["фантастика", "комиксы", "косплей", "сериалы", "компьютерные игры"],
             description="Крупнейший фестиваль поп-культуры. Конкурс косплея, выставочные стенды, Аллея Авторов, настольные и консольные игры, квесты.",
             source_url="https://epiccon.ru/", ticket_url="https://epiccon.ru/", is_confirmed=True),
    Festival(name="АниКон", date_start="2026-07-17", date_end="2026-07-19", venue="Санкт-Петербург",
             city="Санкт-Петербург", themes=["аниме", "косплей", "японская культура"],
             description="Аниме-фестиваль с сильной сценической программой и косплей-дефиле.",
             source_url="https://vk.com/aniconspb", is_confirmed=True),
    Festival(name="DiceFest IV", date_start="2026-07-25", date_end="2026-07-26", venue="Санкт-Петербург",
             city="Санкт-Петербург", themes=["ролевые игры", "настольные игры", "НРИ"],
             description="Фестиваль настольных ролевых игр. Игротеки, мастер-классы, новые знакомства.",
             source_url="https://taplink.cc/rurpgfest", is_confirmed=True),
    Festival(name="ДАНЖН ФЕСТ", date_start="2026-08-01", date_end="2026-08-02", venue="Санкт-Петербург",
             city="Санкт-Петербург", themes=["ролевые игры", "фэнтези", "НРИ"],
             description="Фестиваль настольных ролевых игр в жанре dungeon crawl.",
             source_url="https://taplink.cc/rurpgfest", is_confirmed=True),
    Festival(name="Япония.Фест", date_start="2026-05-22", date_end="2026-09-06", venue="Санкт-Петербург",
             city="Санкт-Петербург", themes=["аниме", "японская культура", "субкультуры"],
             description="Долгосрочная выставочная программа японской культуры.",
             source_url="https://vk.com/japanfestspb", is_confirmed=True),
    Festival(name="ToshoCon", date_start="2026-09-15", date_end="2026-09-17", venue="Санкт-Петербург",
             city="Санкт-Петербург", themes=["аниме", "японская культура", "косплей"],
             description="Крупный аниме-фестиваль с упором на японскую культуру. Точные даты уточняются.",
             source_url="https://vk.com/toshocon", is_confirmed=False),
]

def generate_google_calendar_link(festival):
    base_url = "https://www.google.com/calendar/render"
    start = festival.date_start.replace("-", "")
    if festival.date_end:
        end_dt = datetime.strptime(festival.date_end, "%Y-%m-%d") + timedelta(days=1)
        end = end_dt.strftime("%Y%m%d")
    else:
        end = start
    params = {
        "action": "TEMPLATE", "text": festival.name, "dates": f"{start}/{end}",
        "details": f"{festival.description}\n\nИсточник: {festival.source_url}",
        "location": f"{festival.venue}, {festival.city}", "sf": "true", "output": "xml"
    }
    query = "&".join([f"{quote(k, safe='')}={quote(str(v), safe='')}" for k, v in params.items()])
    return f"{base_url}?{query}"

HTML_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Календарь фестивалей - $city</title>
    <style>
        :root { --bg: #0f0f23; --surface: #1a1a2e; --surface-light: #16213e;
                --text: #e0e0e0; --text-muted: #888; --accent: #e94560;
                --accent-secondary: #0f3460; --border: #2a2a4a;
                --success: #4caf50; --warning: #ff9800; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', system-ui, sans-serif;
               background: var(--bg); color: var(--text); line-height: 1.6; }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        header { text-align: center; padding: 3rem 0;
                 border-bottom: 2px solid var(--accent); margin-bottom: 2rem; }
        h1 { font-size: 2.5rem; background: linear-gradient(135deg, var(--accent), #ff6b6b);
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: var(--text-muted); font-size: 1.1rem; }
        .filters { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 2rem;
                  padding: 1rem; background: var(--surface); border-radius: 12px; }
        .filter-btn { padding: 0.5rem 1rem; border: 1px solid var(--border);
                     background: var(--surface-light); color: var(--text);
                     border-radius: 20px; cursor: pointer; transition: all 0.3s; }
        .filter-btn:hover, .filter-btn.active { background: var(--accent); color: white; }
        .months-grid { display: grid; gap: 2rem; }
        .month-section { background: var(--surface); border-radius: 16px;
                         padding: 1.5rem; border: 1px solid var(--border); }
        .month-title { font-size: 1.5rem; color: var(--accent); margin-bottom: 1rem; }
        .festival-card { background: var(--surface-light); border-radius: 12px;
                        padding: 1.25rem; margin-bottom: 1rem;
                        border-left: 4px solid var(--accent); transition: all 0.2s; }
        .festival-card:hover { transform: translateX(5px);
                              box-shadow: 0 4px 20px rgba(233, 69, 96, 0.15); }
        .festival-card.tentative { border-left-color: var(--warning); opacity: 0.85; }
        .festival-header { display: flex; justify-content: space-between;
                          align-items: flex-start; flex-wrap: wrap; gap: 0.5rem; }
        .festival-name { font-size: 1.2rem; font-weight: 600; color: #fff; word-break: break-word; }
        .festival-date { background: var(--accent-secondary); padding: 0.25rem 0.75rem;
                        border-radius: 20px; font-size: 0.85rem; color: #fff; white-space: nowrap; }
        .festival-date.tentative { background: var(--warning); color: #000; }
        .festival-venue { color: var(--text-muted); font-size: 0.9rem; margin: 0.5rem 0; }
        .festival-description { color: var(--text-muted); font-size: 0.95rem; margin-bottom: 0.75rem;
                               line-height: 1.5; }
        .themes { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1rem; }
        .theme-tag { background: rgba(233, 69, 96, 0.15); color: var(--accent);
                    padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.8rem; }
        .actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }
        .btn { padding: 0.5rem 1rem; border-radius: 8px; text-decoration: none;
               font-size: 0.9rem; transition: all 0.2s; display: inline-flex; gap: 0.4rem; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: #ff6b6b; }
        .btn-secondary { background: var(--surface); color: var(--text); border: 1px solid var(--border); }
        .status-badge { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px;
                       font-size: 0.75rem; margin-left: 0.5rem; }
        .status-confirmed { background: rgba(76, 175, 80, 0.2); color: var(--success); }
        .status-tentative { background: rgba(255, 152, 0, 0.2); color: var(--warning); }
        .update-info { text-align: center; padding: 0.5rem; background: var(--surface-light);
                      border-radius: 8px; margin-bottom: 1rem; font-size: 0.9rem;
                      color: var(--text-muted); border: 1px solid var(--border); }
        .update-info .label { color: var(--accent); font-weight: 600; }
        .dedup-info { text-align: center; padding: 0.4rem; background: rgba(76, 175, 80, 0.1);
                      border-radius: 6px; margin-bottom: 1rem; font-size: 0.85rem;
                      color: var(--success); border: 1px solid rgba(76, 175, 80, 0.3); }
        footer { text-align: center; padding: 2rem; color: var(--text-muted);
                 border-top: 1px solid var(--border); margin-top: 2rem; }
        @media (max-width: 768px) { .container { padding: 1rem; } h1 { font-size: 1.8rem; } }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Календарь фестивалей</h1>
            <p class="subtitle">$city &bull; Гик-культура, аниме, ролевые игры, фэнтези, технологии</p>
        </header>
        <div class="update-info">
            <span class="label">Последнее обновление данных:</span> $last_update
        </div>
        <div class="dedup-info">
            Найдено мероприятий: $total_events | Уникальных после фильтрации дублей: $unique_events
        </div>
        <div class="filters">
            <button class="filter-btn active" onclick="filterThemes('all')">Все</button>
            $filter_buttons
        </div>
        <div class="months-grid">$months_content</div>
        <footer>
            <p>Страница сгенерирована: $update_time</p>
            <p>Источники: Epic Con, Ролевой Маяк, AnimeScene, VK Fest</p>
        </footer>
    </div>
    <script>
        function filterThemes(theme) {
            const cards = document.querySelectorAll('.festival-card');
            const buttons = document.querySelectorAll('.filter-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            cards.forEach(card => {
                if (theme === 'all' || card.dataset.themes.includes(theme))
                    card.style.display = 'block';
                else
                    card.style.display = 'none';
            });
        }
    </script>
</body>
</html>""")


def generate_filter_buttons(festivals):
    all_themes = set()
    for f in festivals:
        all_themes.update(f.themes)
    buttons = []
    for theme in sorted(all_themes):
        buttons.append(f"<button class=\"filter-btn\" onclick=\"filterThemes('{theme}')\">{theme}</button>")
    return "\n".join(buttons)

def format_date_range(date_start, date_end):
    start_dt = datetime.strptime(date_start, "%Y-%m-%d")
    if date_end and date_end != date_start:
        end_dt = datetime.strptime(date_end, "%Y-%m-%d")
        if start_dt.month == end_dt.month:
            return f"{start_dt.day}--{end_dt.day} {get_month_name(start_dt.month)}"
        else:
            return f"{start_dt.day} {get_month_name(start_dt.month)} -- {end_dt.day} {get_month_name(end_dt.month)}"
    return f"{start_dt.day} {get_month_name(start_dt.month)}"

def get_month_name(month_num):
    months = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    return months[month_num]

def generate_festival_card(festival):
    date_str = format_date_range(festival.date_start, festival.date_end)
    tentative_class = "tentative" if not festival.is_confirmed else ""
    status_class = "status-tentative" if not festival.is_confirmed else "status-confirmed"
    status_text = "дата уточняется" if not festival.is_confirmed else "подтверждено"
    themes_html = "".join([f"<span class=\"theme-tag\">{t}</span>" for t in festival.themes])
    themes_data = ",".join(festival.themes)
    calendar_link = generate_google_calendar_link(festival)
    return f"""
        <div class="festival-card {tentative_class}" data-themes="{themes_data}">
            <div class="festival-header">
                <span class="festival-name">{festival.name}
                    <span class="status-badge {status_class}">{status_text}</span>
                </span>
                <span class="festival-date {tentative_class}">{date_str}</span>
            </div>
            <div class="festival-venue">{festival.venue}</div>
            <div class="festival-description">{festival.description}</div>
            <div class="themes">{themes_html}</div>
            <div class="actions">
                <a href="{festival.source_url}" class="btn btn-secondary" target="_blank">Подробнее</a>
                <a href="{calendar_link}" class="btn btn-primary" target="_blank">В Google Calendar</a>
            </div>
        </div>
    """

def group_by_month(festivals):
    months = {}
    for f in festivals:
        month_key = f.date_start[:7]
        if month_key not in months:
            months[month_key] = []
        months[month_key].append(f)
    for month in months:
        months[month].sort(key=lambda x: x.date_start)
    return dict(sorted(months.items()))

def generate_months_html(festivals):
    months = group_by_month(festivals)
    month_names = {
        "2026-01": "Январь 2026", "2026-02": "Февраль 2026", "2026-03": "Март 2026",
        "2026-04": "Апрель 2026", "2026-05": "Май 2026", "2026-06": "Июнь 2026",
        "2026-07": "Июль 2026", "2026-08": "Август 2026", "2026-09": "Сентябрь 2026",
        "2026-10": "Октябрь 2026", "2026-11": "Ноябрь 2026", "2026-12": "Декабрь 2026",
        "2027-01": "Январь 2027", "2027-02": "Февраль 2027", "2027-03": "Март 2027",
        "2027-04": "Апрель 2027", "2027-05": "Май 2027", "2027-06": "Июнь 2027",
        "2027-07": "Июль 2027", "2027-08": "Август 2027", "2027-09": "Сентябрь 2027",
        "2027-10": "Октябрь 2027", "2027-11": "Ноябрь 2027", "2027-12": "Декабрь 2027",
    }
    sections = []
    for month_key, fest_list in months.items():
        cards = "\n".join([generate_festival_card(f) for f in fest_list])
        month_name = month_names.get(month_key, month_key)
        sections.append(f"""
            <div class="month-section">
                <h2 class="month-title">{month_name}</h2>
                {cards}
            </div>
        """)
    return "\n".join(sections)

def build_calendar():
    vk_festivals, last_vk_update = scrape_vk_festivals()
    if vk_festivals:
        festivals = vk_festivals
        print(f"Using {len(vk_festivals)} festivals from VK API")
    else:
        festivals = SAMPLE_FESTIVALS
        last_vk_update = "данные из кэша (VK API недоступен)"
        print(f"VK API returned no data, using {len(SAMPLE_FESTIVALS)} sample festivals")

    # Count before dedup for display
    total_raw = len(festivals)
    festivals = deduplicate_festivals(festivals)
    unique_count = len(festivals)
    print(f"Deduplication: {total_raw} raw -> {unique_count} unique")

    Path("public").mkdir(exist_ok=True)

    html = HTML_TEMPLATE.substitute(
        city=CITY,
        last_update=last_vk_update,
        total_events=total_raw,
        unique_events=unique_count,
        filter_buttons=generate_filter_buttons(festivals),
        months_content=generate_months_html(festivals),
        update_time=datetime.now(MSK).strftime("%d %B %Y, %H:%M")
    )
    with open(HTML_OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Название", "Дата начала", "Дата окончания", "Место", "Темы",
                         "Описание", "Ссылка", "Google Calendar"])
        for fest in festivals:
            writer.writerow([
                fest.name, fest.date_start, fest.date_end or "",
                fest.venue, ", ".join(fest.themes),
                fest.description, fest.source_url,
                generate_google_calendar_link(fest)
            ])
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([f.to_dict() for f in festivals], f, ensure_ascii=False, indent=2)
    print("Calendar built successfully!")
    print(f"   HTML: {HTML_OUTPUT}")
    print(f"   CSV: {CSV_OUTPUT}")
    print(f"   JSON: {DATA_FILE}")
    print(f"   Total festivals: {len(festivals)}")

if __name__ == "__main__":
    build_calendar()
