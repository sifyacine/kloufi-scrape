#!/usr/bin/env python3
"""
Local Testing Runner

Runs scrapers in local testing mode:
- Saves data to junk_test/ instead of Elasticsearch
- Uses reduced concurrency for debugging
- More verbose logging

Usage:
    python scripts/local_test.py --category immobilier --site ouedkniss
    python scripts/local_test.py --category voiture --single-run
"""

import asyncio
import sys
import os
from pathlib import Path

# Set environment BEFORE importing config
os.environ["KLOUFI_ENV"] = "local"

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import print_config_summary, get_data_path, CATEGORIES
from core.dispatcher import ScraperDispatcher
import argparse


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run scrapers in local testing mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--category", "-c",
        choices=CATEGORIES,
        help="Category to scrape (default: all)"
    )
    
    parser.add_argument(
        "--site", "-s",
        help="Specific site to scrape"
    )
    
    parser.add_argument(
        "--single-run",
        action="store_true",
        default=True,
        help="Run once and exit (default for local testing)"
    )
    
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously (override single-run)"
    )
    
    return parser.parse_args()


async def main():
    args = parse_args()
    
    print("\n" + "="*60)
    print("KLOUFI-SCRAPE LOCAL TESTING MODE")
    print("="*60)
    
    # Show configuration
    print_config_summary()
    
    print(f"Output directory: {get_data_path()}")
    print("="*60 + "\n")
    
    # Setup categories
    categories = [args.category] if args.category else None
    
    # Determine if single run
    single_run = not args.continuous
    
    # Create and run dispatcher
    dispatcher = ScraperDispatcher(
        categories=categories,
        single_run=single_run,
    )
    
    await dispatcher.run()


if __name__ == "__main__":
    asyncio.run(main())
