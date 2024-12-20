import os
import logging
import asyncio
from config import (
    GAMERPOWER_GAMES_CONFIG,
    GAMERPOWER_LOOT_CONFIG,
    ITCHIO_GAMES_CONFIG,
    IVY_LEAGUE_CONFIG,
    FEEDS
)
from feed_processor import process_feed_with_db
from gamerpower_processor import process_single_gamerpower_feed
from db_manager import DBManager
from utils import setup_logging
from datetime import datetime
import pytz

# Set environment variables
os.environ["TURSO_DATABASE_URL"] = "libsql://main-goodoffers-db-offren.turso.io"
os.environ["TURSO_AUTH_TOKEN"] = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3MzExMjg1MzYsImlkIjoiNzgwNDY1YjktNzc5Yi00YjNhLTgwYzUtZWVlN2Q5NzUxNWI3In0.v7X1lyPpxDOUk123E3EHjTBJ8_LBtFvwOkVylqz9edu2dQjznSe87oBFtRSrNk1PD6OCpmNoiBP31NnGY4HEDA"

async def process_gamerpower_feed(config: dict, db_manager: DBManager) -> None:
    """Process GamerPower feed and store items in database."""
    try:
        results = process_single_gamerpower_feed(config)
        if results:
            for result in results:
                # Add source URL and current time
                result['pub_date'] = datetime.now(pytz.UTC)
                result['feed_config'] = config
                await db_manager.add_feed_item(result)
    except Exception as e:
        logging.error(f"Error processing GamerPower feed: {str(e)}")

async def main():
    setup_logging()
    logging.info("Starting feed generation")

    db_manager = DBManager()
    try:
        # Process GamerPower feeds
        await process_gamerpower_feed(GAMERPOWER_GAMES_CONFIG, db_manager)
        await process_gamerpower_feed(GAMERPOWER_LOOT_CONFIG, db_manager)

        # Process Itch.io feed
        results = await process_feed_with_db(ITCHIO_GAMES_CONFIG, db_manager)
        if results:
            for result in results:
                await db_manager.add_feed_item(result)

        # Process Ivy League feed
        results = await process_feed_with_db(IVY_LEAGUE_CONFIG, db_manager)
        if results:
            for result in results:
                await db_manager.add_feed_item(result)

        # Process Udemy feeds
        for feed_config in FEEDS:
            results = await process_feed_with_db(feed_config, db_manager)
            if results:
                for result in results:
                    await db_manager.add_feed_item(result)

    finally:
        await db_manager.close()

if __name__ == "__main__":
    asyncio.run(main())