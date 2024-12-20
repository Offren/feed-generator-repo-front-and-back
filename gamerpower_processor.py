import logging
import time
from typing import List, Dict, Any
import urllib.parse
from datetime import datetime
import pytz
import requests
from lxml import html
import feedparser
from utils import get_headers
from config import GAMERPOWER_LOOT_CONFIG, GAMERPOWER_GAMES_CONFIG

def fetch_url_with_retry(url: str) -> requests.Response:
    """Fetch URL with retry mechanism."""
    for attempt in range(3):  # MAX_RETRIES = 3
        try:
            headers = get_headers()
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logging.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
            if attempt < 2:  # MAX_RETRIES - 1
                time.sleep(5)  # RETRY_DELAY = 5
            else:
                raise
    return requests.Response()

def get_absolute_url(url: str, base_url: str) -> str:
    """Convert relative URLs to absolute URLs."""
    if url.startswith(('http://', 'https://')):
        return url
    return urllib.parse.urljoin(base_url, url)

def determine_feed_type(config: Dict) -> str:
    """Determine feed type based on config."""
    logging.info(f"Determining GamerPower feed type")
    logging.info(f"Config RSS URL: {config['rss_url']}")
    logging.info(f"LOOT config RSS URL: {GAMERPOWER_LOOT_CONFIG['rss_url']}")
    logging.info(f"GAMES config RSS URL: {GAMERPOWER_GAMES_CONFIG['rss_url']}")

    if config['rss_url'] == GAMERPOWER_LOOT_CONFIG['rss_url']:
        logging.info("Matched LOOT config - returning DLC")
        return 'DLC'
    elif config['rss_url'] == GAMERPOWER_GAMES_CONFIG['rss_url']:
        logging.info("Matched GAMES config - returning Videogame")
        return 'Videogame'
    
    logging.warning(f"No config match found, defaulting to Videogame")
    return 'Videogame'

def process_single_gamerpower_feed(config: Dict) -> List[Dict[str, Any]]:
    """Process a single GamerPower RSS feed and extract items."""
    results = []
    logging.info(f"Parsing GamerPower RSS feed: {config['rss_url']}")
    feed = feedparser.parse(config['rss_url'])

    # Determine feed type once for all items in this feed
    feed_type = determine_feed_type(config)
    logging.info(f"Feed type determined as: {feed_type}")

    if not feed.entries:
        logging.warning(f"No entries found in the GamerPower RSS feed: {config['rss_url']}")
        return results

    for entry in feed.entries[:config['max_entries']]:
        url = entry.get('link')
        if not url:
            logging.warning(f"Entry does not have a link: {entry.get('title', 'Untitled')}")
            continue

        logging.info(f"Processing entry: {url}")

        try:
            response = fetch_url_with_retry(url)
            tree = html.fromstring(response.content)
            elements = tree.xpath(config['xpath'])

            if elements:
                content = elements[0]
                full_url = urllib.parse.urljoin(config['base_url'], content)
                
                # Extract image URL using image_xpath
                image_url = None
                if 'image_xpath' in config:
                    image_elements = tree.xpath(config['image_xpath'])
                    if image_elements:
                        image_url = get_absolute_url(image_elements[0], config['base_url'])

                # Generate unique hash for the item
                item_hash = f"{hash(full_url + entry.get('title', ''))}"[:7]
                
                result = {
                    'title': entry.get('title', 'Untitled'),
                    'description': entry.get('description', '')[:500] + '...',
                    'link': full_url,
                    'image_url': image_url,
                    'item_hash': item_hash,
                    'source_url': config['base_url'],
                    'feed_config': {
                        'rss_url': config['rss_url'],
                        'base_url': config['base_url']
                    },
                    'feed_type': feed_type  # Set feed type directly here
                }
                
                results.append(result)
                logging.info(f"Found matching content using XPath for {url}")
            else:
                logging.warning(f"No content found using XPath for {url}")

        except Exception as e:
            logging.error(f"Error processing {url}: {e}")

    return results