"""
Kloufi-Scrape Dispatcher

Main orchestrator for continuous auto-scraping across all categories.
Manages scraping cycles, category scheduling, and graceful shutdown.
"""

import asyncio
import signal
import sys
import importlib
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    get_environment,
    get_scraper_config,
    get_schedule_config,
    CATEGORIES,
    print_config_summary,
)
from core.alerting import get_alert_manager, cleanup_alerts, AlertLevel
from scraper.utils.logger import get_logger
from scraper.proxy.proxy_sources import fetch_proxies
from scraper.proxy.proxy_manager import ProxyManager

logger = get_logger("dispatcher")


class ScraperDispatcher:
    """
    Main dispatcher that orchestrates scraping across all categories.
    
    Responsibilities:
    - Manage scraping lifecycle (start, stop, pause)
    - Schedule category scraping
    - Handle graceful shutdown
    - Report progress and errors
    """
    
    def __init__(
        self,
        categories: Optional[List[str]] = None,
        single_run: bool = False,
    ):
        self.categories = categories or CATEGORIES
        self.single_run = single_run
        self.config = get_scraper_config()
        self.schedule_config = get_schedule_config()
        self.alert_manager = get_alert_manager()
        
        # State tracking
        self._running = False
        self._current_category: Optional[str] = None
        self._cycle_count = 0
        self._start_time: Optional[datetime] = None
        self._category_stats: Dict[str, Dict[str, Any]] = {}
        
        # Proxy management (shared across all scrapers)
        self._proxy_manager: Optional[ProxyManager] = None
        
        # Shutdown handling
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self):
        """Initialize dispatcher resources."""
        logger.info("Initializing dispatcher...")
        
        # Fetch proxies if enabled
        if self.config.use_proxies:
            logger.info("Fetching proxies...")
            try:
                proxies = await fetch_proxies()
                self._proxy_manager = ProxyManager(proxies)
                logger.info(f"Loaded {len(proxies)} proxies")
            except Exception as e:
                logger.warning(f"Failed to fetch proxies: {e}")
                self._proxy_manager = None
        
        # Initialize stats for each category
        for category in self.categories:
            self._category_stats[category] = {
                "items_scraped": 0,
                "errors": 0,
                "last_run": None,
                "duration": 0,
            }
        
        logger.info(f"Dispatcher initialized for categories: {self.categories}")
    
    async def run_category(self, category: str) -> Dict[str, Any]:
        """
        Run scraper for a single category.
        
        Returns dict with scraping results.
        """
        self._current_category = category
        start_time = datetime.now()
        items_scraped = 0
        errors = 0
        
        logger.info(f"Starting scrape for category: {category}")
        
        try:
            # Dynamically import and run the category scraper
            scraper_module = self._get_scraper_module(category)
            
            if scraper_module is None:
                logger.warning(f"No scraper found for category: {category}")
                return {"items_scraped": 0, "errors": 1, "status": "no_scraper"}
            
            # Run the scraper with timeout
            timeout = self.schedule_config.max_category_runtime
            
            try:
                result = await asyncio.wait_for(
                    scraper_module.run(
                        proxy_manager=self._proxy_manager,
                        config=self.config,
                        shutdown_event=self._shutdown_event,
                    ),
                    timeout=timeout
                )
                items_scraped = result.get("items_scraped", 0)
                errors = result.get("errors", 0)
                
            except asyncio.TimeoutError:
                logger.warning(f"Category {category} timed out after {timeout}s")
                await self.alert_manager.alert(
                    f"Category `{category}` timed out after {timeout/60:.0f} minutes",
                    AlertLevel.WARNING
                )
            
        except Exception as e:
            logger.error(f"Error running category {category}: {e}")
            logger.error(traceback.format_exc())
            errors += 1
            await self.alert_manager.on_scrape_error(category, "", str(e))
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Update stats
        self._category_stats[category].update({
            "items_scraped": self._category_stats[category]["items_scraped"] + items_scraped,
            "errors": self._category_stats[category]["errors"] + errors,
            "last_run": datetime.now().isoformat(),
            "duration": duration,
        })
        
        # Report completion
        await self.alert_manager.on_category_complete(category, items_scraped, duration)
        
        logger.info(f"Completed {category}: {items_scraped} items in {duration:.0f}s")
        
        self._current_category = None
        
        return {
            "items_scraped": items_scraped,
            "errors": errors,
            "duration": duration,
            "status": "completed",
        }
    
    def _get_scraper_module(self, category: str):
        """
        Get the scraper module for a category.
        
        Tries to import from sites/{category}/dispatcher.py
        Falls back to a generic runner if not found.
        """
        try:
            # Try category-specific dispatcher
            module_path = f"sites.{category}.dispatcher"
            module = importlib.import_module(module_path)
            return module
        except ImportError:
            logger.debug(f"No dispatcher found at {module_path}")
        
        try:
            # Try the generic category runner
            from core import category_runner
            return category_runner.get_runner(category)
        except ImportError as e:
            logger.warning(f"Could not load runner for {category}: {e}")
            return None
    
    async def run_cycle(self) -> Dict[str, int]:
        """
        Run one complete scraping cycle across all categories.
        
        Returns dict of items scraped per category.
        """
        self._cycle_count += 1
        cycle_start = datetime.now()
        results = {}
        
        logger.info(f"Starting scrape cycle #{self._cycle_count}")
        
        for i, category in enumerate(self.categories):
            if self._shutdown_event.is_set():
                logger.info("Shutdown requested, stopping cycle")
                break
            
            # Apply category delay (stagger requests)
            delay = self.schedule_config.category_delays.get(category, 0)
            if delay > 0 and i > 0:
                logger.info(f"Waiting {delay}s before starting {category}")
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=delay
                    )
                    # If we get here, shutdown was requested
                    break
                except asyncio.TimeoutError:
                    pass  # Normal, delay completed
            
            # Run the category
            result = await self.run_category(category)
            results[category] = result.get("items_scraped", 0)
        
        cycle_duration = (datetime.now() - cycle_start).total_seconds()
        
        # Report cycle completion
        await self.alert_manager.on_cycle_complete(results, cycle_duration)
        
        logger.info(f"Cycle #{self._cycle_count} complete: {sum(results.values())} items in {cycle_duration/60:.1f} min")
        
        return results
    
    async def run(self):
        """
        Main run loop. Runs scraping cycles continuously until shutdown.
        """
        self._running = True
        self._start_time = datetime.now()
        
        # Print configuration
        print_config_summary()
        
        # Initialize
        await self.initialize()
        
        # Send startup notification
        await self.alert_manager.on_startup(self.categories)
        
        logger.info("=" * 60)
        logger.info("KLOUFI SCRAPER STARTED")
        logger.info(f"Mode: {'Single Run' if self.single_run else 'Continuous'}")
        logger.info(f"Categories: {self.categories}")
        logger.info("=" * 60)
        
        try:
            while self._running and not self._shutdown_event.is_set():
                # Run a scraping cycle
                await self.run_cycle()
                
                # Exit if single run mode
                if self.single_run:
                    logger.info("Single run complete, exiting")
                    break
                
                # Wait before next cycle
                cycle_delay = self.schedule_config.cycle_delay
                logger.info(f"Waiting {cycle_delay/60:.0f} minutes before next cycle...")
                
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=cycle_delay
                    )
                    # Shutdown requested during wait
                    break
                except asyncio.TimeoutError:
                    pass  # Normal, delay completed
                
        except asyncio.CancelledError:
            logger.info("Dispatcher cancelled")
        except Exception as e:
            logger.error(f"Dispatcher error: {e}")
            logger.error(traceback.format_exc())
            await self.alert_manager.alert(
                f"*Dispatcher Error*\n`{str(e)}`",
                AlertLevel.CRITICAL
            )
        finally:
            await self.shutdown()
    
    async def shutdown(self, reason: str = "Normal shutdown"):
        """Graceful shutdown."""
        if not self._running:
            return
        
        logger.info(f"Shutting down: {reason}")
        self._running = False
        self._shutdown_event.set()
        
        # Send shutdown notification
        await self.alert_manager.on_shutdown(reason)
        
        # Cleanup
        await cleanup_alerts()
        
        # Log final stats
        total_items = sum(s["items_scraped"] for s in self._category_stats.values())
        total_errors = sum(s["errors"] for s in self._category_stats.values())
        
        if self._start_time:
            runtime = (datetime.now() - self._start_time).total_seconds()
            logger.info(f"Total runtime: {runtime/3600:.1f} hours")
        
        logger.info(f"Total items scraped: {total_items}")
        logger.info(f"Total errors: {total_errors}")
        logger.info("Dispatcher shutdown complete")
    
    def request_shutdown(self, reason: str = "Manual stop"):
        """Request graceful shutdown (can be called from signal handlers)."""
        logger.info(f"Shutdown requested: {reason}")
        self._shutdown_event.set()


# ============================================================================
# SIGNAL HANDLING
# ============================================================================

_dispatcher: Optional[ScraperDispatcher] = None


def setup_signal_handlers(dispatcher: ScraperDispatcher):
    """Setup signal handlers for graceful shutdown."""
    global _dispatcher
    _dispatcher = dispatcher
    
    def signal_handler(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info(f"Received signal: {sig_name}")
        if _dispatcher:
            _dispatcher.request_shutdown(f"Signal {sig_name}")
    
    # Register handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Windows doesn't have SIGHUP
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, signal_handler)


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Kloufi-Scrape Dispatcher - Orchestrates web scraping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all categories continuously
  python dispatcher.py

  # Run specific categories
  python dispatcher.py --categories immobilier voiture

  # Single run (scrape once and exit)
  python dispatcher.py --single-run

  # Local testing mode
  KLOUFI_ENV=local python dispatcher.py --single-run --categories immobilier
        """
    )
    
    parser.add_argument(
        "--categories", "-c",
        nargs="+",
        choices=CATEGORIES,
        default=None,
        help="Categories to scrape (default: all)"
    )
    
    parser.add_argument(
        "--single-run", "-s",
        action="store_true",
        help="Run once and exit (don't loop)"
    )
    
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="List available categories and exit"
    )
    
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    
    if args.list_categories:
        print("Available categories:")
        for cat in CATEGORIES:
            print(f"  - {cat}")
        return
    
    # Create dispatcher
    dispatcher = ScraperDispatcher(
        categories=args.categories,
        single_run=args.single_run,
    )
    
    # Setup signal handlers
    setup_signal_handlers(dispatcher)
    
    # Run
    await dispatcher.run()


if __name__ == "__main__":
    asyncio.run(main())
