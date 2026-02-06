import requests
from bs4 import BeautifulSoup
import re

# List of specific public Telegram channels (usernames without @, e.g., 'v2ray_configs')
channels = ['ConfigV2rayNG', 'SOSkeyNET', 'lebertad', 'ConfigsHUB2', 'filembad', 'V2All']

# Regex for V2Ray configs (vmess://, vless://, etc.)
config_pattern = re.compile(r'(vmess://|vless://|trojan://)[A-Za-z0-9+/=]+')

def scrape_channel(channel):
    url = f'https://t.me/s/{channel}'
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        messages = soup.find_all('div', class_='tgme_widget_message_text')
        configs = set()
        for msg in messages:
            text = msg.get_text(strip=True)
            matches = config_pattern.findall(text)
            configs.update(matches)
        return configs
    except Exception as e:
        print(f"Error scraping {channel}: {e}")
        return set()

all_configs = set()
for channel in channels:
    all_configs.update(scrape_channel(channel))

# Save to file
with open('configs.txt', 'w') as f:
    for config in sorted(all_configs):
        f.write(config + '\n')

print(f"Saved {len(all_configs)} configs")
