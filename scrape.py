import re
import json
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import random
import time
import urllib.parse

CONFIG_REGEX = re.compile(
    r'(vmess://[^\s<>\[\]]+|vless://[^\s<>\[\]]+|trojan://[^\s<>\[\]]+|ss://[^\s<>\[\]]+|hysteria2://[^\s<>\[\]]+|hysteria://[^\s<>\[\]]+)'
)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CHANNELS_FILE = "channels.json"
MAX_CONFIGS_PER_CHANNEL = 300      # reduced from 500 - keeps most recent 300 per channel
MAX_PAGES_PER_CHANNEL = 12         # adjust as needed (5–20)
REQUEST_TIMEOUT = 25

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

def clean_and_normalize_config(raw_link: str, index: int = 0) -> str:
    """Parse link and create a clean, meaningful remark"""
    try:
        parsed = urllib.parse.urlparse(raw_link)
        qs = urllib.parse.parse_qs(parsed.query)

        remark = qs.get('remark', [''])[0].strip()
        remark = re.sub(r'[^\w\s\-:]', '', remark)  # strip emojis & junk

        if remark and len(remark) > 4:  # use only if it looks useful
            if len(remark) > 60:
                remark = remark[:57] + "..."
        else:
            # Improved fallback naming
            host = parsed.hostname or "unknown"
            port_str = f":{parsed.port}" if parsed.port else ""
            proto = parsed.scheme.upper()

            # Add uniqueness if many similar configs
            extra = ""
            if index > 0 and index % 5 == 0:  # every 5th gets numbered
                extra = f" #{index}"
            elif '#' in raw_link:
                frag = raw_link.split('#')[-1][:8].strip()
                if frag and len(frag) > 3:
                    extra = f" #{frag}"

            remark = f"{host}{port_str} - {proto}{extra}"

        # Rebuild the link with cleaned remark (preserve other params)
        new_qs = {k: v for k, v in qs.items() if k != 'remark'}
        new_qs['remark'] = [remark]
        new_query = urllib.parse.urlencode(new_qs, doseq=True)

        clean_link = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment or ''
        ))

        return clean_link
    except Exception:
        # Last resort fallback
        fallback_remark = f"Config-{index}" if index > 0 else "Config"
        sep = '&' if '?' in raw_link else '?'
        return f"{raw_link}{sep}remark={fallback_remark}"


def scrape_channel(base_url: str, name: str):
    print(f"\nScraping {name} ({base_url}) ...")
    all_configs = set()  # dedup across pages
    url = base_url.rstrip('/')
    page_count = 0
    global_index = 0

    while page_count < MAX_PAGES_PER_CHANNEL:
        page_count += 1
        print(f"  Page {page_count} → {url}")
        try:
            time.sleep(random.uniform(2.0, 5.5))
            r = requests.get(url, headers=get_random_headers(), timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
        except Exception as e:
            print(f"  → Request failed: {e}")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        message_wrappers = soup.select("div.tgme_widget_message[data-post]")

        if not message_wrappers:
            print("  → No messages found (end of channel or class changed)")
            break

        page_new_count = 0
        oldest_msg_id = None

        for wrapper in message_wrappers:
            text_elem = wrapper.select_one("div.tgme_widget_message_text")
            if not text_elem:
                continue

            text = text_elem.get_text(separator=" ", strip=True)
            found_links = CONFIG_REGEX.findall(text)

            for raw_link in found_links:
                global_index += 1
                clean_link = clean_and_normalize_config(raw_link, index=global_index)
                if clean_link not in all_configs:
                    all_configs.add(clean_link)
                    page_new_count += 1

            # Find oldest message ID for next page
            data_post = wrapper.get("data-post")
            if data_post:
                try:
                    _, msg_id_str = data_post.rsplit("/", 1)
                    msg_id = int(msg_id_str)
                    if oldest_msg_id is None or msg_id < oldest_msg_id:
                        oldest_msg_id = msg_id
                except:
                    pass

        print(f"  → Added {page_new_count} new unique configs (total: {len(all_configs)})")

        if oldest_msg_id is None or oldest_msg_id <= 1:
            break

        url = f"{base_url}?before={oldest_msg_id}"

    # Save result
    configs_list = list(all_configs)
    print(f"→ Total unique configs after {page_count} pages: {len(configs_list)}")

    outfile = DATA_DIR / f"{name}.txt"
    old_configs = []
    if outfile.is_file():
        with open(outfile, encoding="utf-8") as f:
            old_configs = [line.strip() for line in f if line.strip()]

    # Keep only the most recent 300 (newest first since we scrape recent → older)
    combined = list(dict.fromkeys(configs_list + old_configs))[:MAX_CONFIGS_PER_CHANNEL]

    with open(outfile, "w", encoding="utf-8") as f:
        f.write("\n".join(combined) + "\n")

    print(f"→ Saved {len(combined)} configs (limited to {MAX_CONFIGS_PER_CHANNEL}) → {outfile}")


def main():
    if not Path(CHANNELS_FILE).is_file():
        print(f"Error: {CHANNELS_FILE} not found!")
        return

    with open(CHANNELS_FILE, encoding="utf-8") as f:
        channels = json.load(f)

    for name, url in channels.items():
        if not url.startswith("https://t.me/s/"):
            print(f"Skipping {name}: URL should start with https://t.me/s/")
            continue
        scrape_channel(url, name)


if __name__ == "__main__":
    main()
