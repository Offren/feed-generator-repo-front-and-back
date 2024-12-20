import feedparser
import requests
from lxml import html
from typing import List, Dict, Optional
from datetime import datetime
import pytz
import urllib.parse
import hashlib
import logging
from db_manager import DBManager
from utils import make_request, get_headers
from config import GAMERPOWER_LOOT_CONFIG, GAMERPOWER_GAMES_CONFIG

def generate_item_hash(title: str, link: str) -> str:
    """Generate a unique hash for each feed item based on title and link."""
    content = f"{title}{link}".encode('utf-8')
    return hashlib.sha256(content).hexdigest()[:7]

def determine_item_class(result: Dict) -> str:
    """Determine the class of the feed item based on its source and feed config."""
    source_url = result.get('source_url', '').lower()
    feed_config = result.get('feed_config', {})
    
    # Check if this is from GamerPower
    if 'gamerpower.com' in source_url:
        # Log the comparison details
        logging.info(f"Checking GamerPower feed type for {result['title']}")
        logging.info(f"Feed config: {feed_config}")
        logging.info(f"LOOT config: {GAMERPOWER_LOOT_CONFIG}")
        logging.info(f"GAMES config: {GAMERPOWER_GAMES_CONFIG}")
        
        # Compare RSS URLs instead of entire configs
        if feed_config.get('rss_url') == GAMERPOWER_LOOT_CONFIG['rss_url']:
            logging.info("Matched LOOT config")
            return 'DLC'
        elif feed_config.get('rss_url') == GAMERPOWER_GAMES_CONFIG['rss_url']:
            logging.info("Matched GAMES config")
            return 'Videogame'
        
        logging.warning(f"No config match found, defaulting to Videogame")
        return 'Videogame'  # Default to Videogame if config not recognized
    
    # Handle other sources
    if 'itch.io' in source_url:
        return 'itchio_game'
    elif 'classcentral.com' in source_url:
        return 'Ivy_League_Course'
    elif any(domain in source_url for domain in ['real.discount', 'scrollcoupons.com', 'onlinecourses.ooo', 'infognu.com', 'jucktion.com']):
        return 'Udemy_Course'
    
    return 'unknown'

async def process_feed_with_db(feed_config: Dict, db_manager: DBManager) -> Optional[List[Dict]]:
    """Process a single feed configuration and store items in database."""
    try:
        feed = feedparser.parse(feed_config['rss_url'])
        results = []
        
        for entry in feed.entries[:feed_config['max_entries']]:
            try:
                source_url = feed_config['base_url']
                result = None  # Initialize result as None
                
                # Create base result dictionary with common fields
                base_result = {
                    'title': entry.title,
                    'description': entry.get('description', '')[:500] + '...',
                    'pub_date': datetime.now(pytz.UTC),
                    'source_url': source_url,
                    'feed_config': {
                        'rss_url': feed_config['rss_url'],
                        'base_url': feed_config['base_url']
                    }  # Only pass necessary config fields
                }

                # For feeds that need XPath processing
                if 'xpath' in feed_config:
                    with requests.Session() as session:
                        content = make_request(entry.link, session)
                        if content:  # Only process if we got content
                            tree = html.fromstring(content)
                            urls = tree.xpath(feed_config['xpath'])
                            
                            if urls:
                                url = urls[0]
                                if not url.startswith(('http://', 'https://')):
                                    url = urllib.parse.urljoin(source_url, url)
                                
                                # Extract image URL using image_xpath
                                image_url = None
                                if 'image_xpath' in feed_config:
                                    image_elements = tree.xpath(feed_config['image_xpath'])
                                    if image_elements:
                                        raw_image_url = image_elements[0]
                                        image_url = clean_image_url(raw_image_url)
                                
                                result = {
                                    **base_result,
                                    'link': url,
                                    'item_hash': generate_item_hash(entry.title, url)
                                }
                                
                                if image_url:
                                    result['image_url'] = image_url
                else:
                    # Direct RSS feed processing (e.g., for Itch.io)
                    result = {
                        **base_result,
                        'link': entry.link,
                        'item_hash': generate_item_hash(entry.title, entry.link)
                    }
                    
                    # Extract image from enclosures if available
                    if hasattr(entry, 'enclosures') and entry.enclosures:
                        for enclosure in entry.enclosures:
                            if enclosure.get('type', '').startswith('image/'):
                                result['image_url'] = enclosure.href
                                break
                
                # Only process if we have a valid result
                if result:
                    # Determine feed type
                    result['feed_type'] = determine_item_class(result)
                    logging.info(f"Determined feed type {result['feed_type']} for {result['title']}")
                    
                    # Store in database
                    await db_manager.add_feed_item(result)
                    results.append(result)
                
            except Exception as e:
                logging.error(f"Error processing entry {entry.link}: {str(e)}")
                continue
                    
        return results
    except Exception as e:
        logging.error(f"Error processing feed {feed_config['rss_url']}: {str(e)}")
        return None

def get_absolute_url(url: str, base_url: str) -> str:
    """Convert relative URLs to absolute URLs."""
    if url.startswith(('http://', 'https://')):
        return url
    return urllib.parse.urljoin(base_url, url)

def clean_image_url(url: str) -> Optional[str]:
    """Clean and validate image URL."""
    if not url:
        return None
    
    # Remove any "/h" suffix
    if url.endswith('/h'):
        url = url[:-2]
    
    # Ensure Udemy image URLs have the correct format
    if 'udemycdn.com' in url:
        # Extract the course ID and image name from the URL
        parts = url.split('/')
        if len(parts) >= 2:
            course_id = parts[-2]
            image_name = parts[-1]
            return f"https://img-c.udemycdn.com/course/750x422/{course_id}_{image_name}"
    
    return url