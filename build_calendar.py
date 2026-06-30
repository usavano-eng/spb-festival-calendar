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
# SAMPLE DATA (fallback when VK_TOKEN is not set or VK fails)
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

def generate_google_calendar_link(festival):
    base_url = 'https://www.google.com/calendar/render'
    start = festival.date_start.replace('-', '')
    if festival.date_end:
        end_dt = datetime.strptime(festival.date_end, '%Y-%m-%d') + timedelta(days=1)
        end = end_dt.strftime('%Y%m%d')
    else:
        end = start
    params = {
        'action': 'TEMPLATE',
        'text': festival.name,
        'dates': f'{start}/{end}',
        'details': f'{festival.description}\n\nИсточник: {festival.source_url}',
        'location': f'{festival.venue}, {festival.city}',
        'sf': 'true',
        'output': 'xml'
    }
    query = '&'.join([f"{quote(k, safe='')}={quote(str(v), safe='')}" for k, v in params.items()])
    return f'{base_url}?{query}'

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang='ru'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Календарь фестивалей - {city}</title>
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
        .festival-name { font-size: 1.2rem; font-weight: 600; color: #fff; }
        .festival-date { background: var(--accent-secondary); padding: 0.25rem 0.75rem;
                        border-radius: 20px; font-size: 0.85rem; color: #fff; }
        .festival-date.tentative { background: var(--warning); color: #000; }
        .festival-venue { color: var(--text-muted); font-size: 0.9rem; margin: 0.5rem 0; }
        .festival-description { color: var(--text-muted); font-size: 0.95rem; margin-bottom: 0.75rem; }
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
        footer { text-align: center; padding: 2rem; color: var(--text-muted);
                 border-top: 1px solid var(--border); margin-top: 2rem; }
        @media (max-width: 768px) { .container { padding: 1rem; } h1 { font-size: 1.8rem; } }
    </style>
</head>
<body>
    <div class='container'>
        <header>
            <h1>Календарь фестивалей</h1>
            <p class='subtitle'>{city} • Гик-культура, аниме, ролевые игры, фэнтези, технологии</p>
        </header>
        <div class='filters'>
            <button class='filter-btn active' onclick="filterThemes('all')">Все</button>
            {filter_buttons}
        </div>
        <div class='months-grid'>{months_content}</div>
        <footer>
            <p>Обновлено: {update_time}</p>
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
</html>'''

def generate_filter_buttons(festivals):
    all_themes = set()
    for f in festivals:
        all_themes.update(f.themes)
    buttons = []
    for theme in sorted(all_themes):
        buttons.append(f"<button class='filter-btn' onclick=\"filterThemes('{theme}')\">{theme}</button>")
    return '\n'.join(buttons)

def format_date_range(date_start, date_end):
    start_dt = datetime.strptime(date_start, '%Y-%m-%d')
    if date_end and date_end != date_start:
        end_dt = datetime.strptime(date_end, '%Y-%m-%d')
        if start_dt.month == end_dt.month:
            return f'{start_dt.day}--{end_dt.day} {get_month_name(start_dt.month)}'
        else:
            return f'{start_dt.day} {get_month_name(start_dt.month)} -- {end_dt.day} {get_month_name(end_dt.month)}'
    return f'{start_dt.day} {get_month_name(start_dt.month)}'

def get_month_name(month_num):
    months = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
              'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
    return months[month_num]

def generate_festival_card(festival):
    date_str = format_date_range(festival.date_start, festival.date_end)
    tentative_class = 'tentative' if not festival.is_confirmed else ''
    status_class = 'status-tentative' if not festival.is_confirmed else 'status-confirmed'
    status_text = 'дата уточняется' if not festival.is_confirmed else 'подтверждено'
    themes_html = ''.join([f"<span class='theme-tag'>{t}</span>" for t in festival.themes])
    themes_data = ','.join(festival.themes)
    calendar_link = generate_google_calendar_link(festival)
    return f'''
        <div class='festival-card {tentative_class}' data-themes='{themes_data}'>
            <div class='festival-header'>
                <span class='festival-name'>{festival.name}
                    <span class='status-badge {status_class}'>{status_text}</span>
                </span>
                <span class='festival-date {tentative_class}'>{date_str}</span>
            </div>
            <div class='festival-venue'>{festival.venue}</div>
            <div class='festival-description'>{festival.description}</div>
            <div class='themes'>{themes_html}</div>
            <div class='actions'>
                <a href='{festival.source_url}' class='btn btn-secondary' target='_blank'>Подробнее</a>
                <a href='{calendar_link}' class='btn btn-primary' target='_blank'>В Google Calendar</a>
            </div>
        </div>
    '''

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
        '2026-01': 'Январь 2026', '2026-02': 'Февраль 2026', '2026-03': 'Март 2026',
        '2026-04': 'Апрель 2026', '2026-05': 'Май 2026', '2026-06': 'Июнь 2026',
        '2026-07': 'Июль 2026', '2026-08': 'Август 2026', '2026-09': 'Сентябрь 2026',
        '2026-10': 'Октябрь 2026', '2026-11': 'Ноябрь 2026', '2026-12': 'Декабрь 2026',
        '2027-01': 'Январь 2027', '2027-02': 'Февраль 2027', '2027-03': 'Март 2027',
        '2027-04': 'Апрель 2027', '2027-05': 'Май 2027', '2027-06': 'Июнь 2027',
        '2027-07': 'Июль 2027', '2027-08': 'Август 2027', '2027-09': 'Сентябрь 2027',
        '2027-10': 'Октябрь 2027', '2027-11': 'Ноябрь 2027', '2027-12': 'Декабрь 2027',
    }
    sections = []
    for month_key, fest_list in months.items():
        cards = '\n'.join([generate_festival_card(f) for f in fest_list])
        month_name = month_names.get(month_key, month_key)
        sections.append(f'''
            <div class='month-section'>
                <h2 class='month-title'>{month_name}</h2>
                {cards}
            </div>
        ''')
    return '\n'.join(sections)

def build_calendar():
    # Try to fetch from VK API first
    vk_festivals = scrape_vk_festivals()

    if vk_festivals:
        festivals = vk_festivals
        print(f"Using {len(vk_festivals)} festivals from VK API")
    else:
        festivals = SAMPLE_FESTIVALS
        print(f"VK API returned no data, using {len(SAMPLE_FESTIVALS)} sample festivals")

    # Ensure public directory exists BEFORE generating files
    Path('public').mkdir(exist_ok=True)

    html = HTML_TEMPLATE.format(
        city=CITY,
        filter_buttons=generate_filter_buttons(festivals),
        months_content=generate_months_html(festivals),
        update_time=datetime.now().strftime('%d %B %Y, %H:%M')
    )
    with open(HTML_OUTPUT, 'w', encoding='utf-8') as f:
        f.write(html)
    with open(CSV_OUTPUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Название', 'Дата начала', 'Дата окончания', 'Место', 'Темы',
                         'Описание', 'Ссылка', 'Google Calendar'])
        for fest in festivals:
            writer.writerow([
                fest.name, fest.date_start, fest.date_end or '',
                fest.venue, ', '.join(fest.themes),
                fest.description, fest.source_url,
                generate_google_calendar_link(fest)
            ])
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump([f.to_dict() for f in festivals], f, ensure_ascii=False, indent=2)
    print('Calendar built successfully!')
    print(f'   HTML: {HTML_OUTPUT}')
    print(f'   CSV: {CSV_OUTPUT}')
    print(f'   JSON: {DATA_FILE}')
    print(f'   Total festivals: {len(festivals)}')

if __name__ == '__main__':
    build_calendar()
