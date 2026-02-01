"""
Kloufi-Scrape Alerting System

Provides real-time alerts via Telegram and Email for:
- Scraping errors
- Block/captcha detection
- System health issues
- Scraping progress reports
"""

import asyncio
import aiohttp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_alert_config, get_environment
from scraper.utils.logger import get_logger

logger = get_logger("alerting")


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "ℹ️"
    WARNING = "⚠️"
    ERROR = "🚨"
    CRITICAL = "🔴"
    SUCCESS = "✅"


@dataclass
class AlertStats:
    """Track alert statistics to avoid spam."""
    consecutive_errors: int = 0
    blocks_detected: int = 0
    captchas_detected: int = 0
    items_scraped: int = 0
    last_alert_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None


class AlertManager:
    """Manages alerts and notifications."""
    
    def __init__(self):
        self.config = get_alert_config()
        self.stats: Dict[str, AlertStats] = {}  # Stats per category
        self._session: Optional[aiohttp.ClientSession] = None
        self._alert_cooldown = 300  # 5 minutes between similar alerts
    
    def get_stats(self, category: str) -> AlertStats:
        """Get or create stats for a category."""
        if category not in self.stats:
            self.stats[category] = AlertStats()
        return self.stats[category]
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    # ========================================================================
    # TELEGRAM ALERTS
    # ========================================================================
    
    async def send_telegram(self, message: str, level: AlertLevel = AlertLevel.INFO) -> bool:
        """Send a Telegram message."""
        if not self.config.telegram_enabled:
            logger.debug("Telegram alerts disabled")
            return False
        
        try:
            session = await self._get_session()
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
            
            # Format message with emoji and timestamp
            env = get_environment().value.upper()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_message = (
                f"{level.value} *KLOUFI [{env}]*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{message}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🕐 {timestamp}"
            )
            
            payload = {
                "chat_id": self.config.telegram_chat_id,
                "text": formatted_message,
                "parse_mode": "Markdown",
            }
            
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    logger.info(f"Telegram alert sent: {level.name}")
                    return True
                else:
                    error = await resp.text()
                    logger.error(f"Telegram send failed: {error}")
                    return False
                    
        except Exception as e:
            logger.error(f"Telegram alert error: {e}")
            return False
    
    # ========================================================================
    # EMAIL ALERTS
    # ========================================================================
    
    def send_email(self, subject: str, body: str, level: AlertLevel = AlertLevel.INFO) -> bool:
        """Send an email alert."""
        if not self.config.email_enabled:
            logger.debug("Email alerts disabled")
            return False
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config.smtp_user
            msg['To'] = self.config.alert_email
            msg['Subject'] = f"[KLOUFI {level.name}] {subject}"
            
            # Format body with HTML
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>{level.value} {subject}</h2>
                <hr>
                <pre>{body}</pre>
                <hr>
                <small>Sent at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</small>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_body, 'html'))
            
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email alert sent: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Email alert error: {e}")
            return False
    
    # ========================================================================
    # ALERT METHODS
    # ========================================================================
    
    async def alert(self, message: str, level: AlertLevel = AlertLevel.INFO) -> bool:
        """Send alert via all configured channels."""
        results = []
        
        if self.config.telegram_enabled:
            results.append(await self.send_telegram(message, level))
        
        if self.config.email_enabled and level in [AlertLevel.ERROR, AlertLevel.CRITICAL]:
            results.append(self.send_email("Scraping Alert", message, level))
        
        return any(results)
    
    async def on_scrape_success(self, category: str, url: str, item_data: Optional[Dict] = None):
        """Record successful scrape."""
        stats = self.get_stats(category)
        stats.items_scraped += 1
        stats.consecutive_errors = 0
        stats.last_success_time = datetime.now()
        
        # Log progress every 100 items
        if stats.items_scraped % 100 == 0:
            await self.alert(
                f"📊 *Progress Report*\n"
                f"Category: `{category}`\n"
                f"Items scraped: {stats.items_scraped}",
                AlertLevel.INFO
            )
    
    async def on_scrape_error(self, category: str, url: str, error: str):
        """Handle scraping error."""
        stats = self.get_stats(category)
        stats.consecutive_errors += 1
        
        logger.error(f"[{category}] Error scraping {url}: {error}")
        
        # Alert if too many consecutive errors
        if stats.consecutive_errors >= self.config.error_threshold:
            await self.alert(
                f"*High Error Rate Detected*\n"
                f"Category: `{category}`\n"
                f"Consecutive errors: {stats.consecutive_errors}\n"
                f"Last URL: `{url}`\n"
                f"Error: `{error[:200]}...`",
                AlertLevel.ERROR
            )
            stats.consecutive_errors = 0  # Reset after alert
    
    async def on_block_detected(self, category: str, url: str, block_type: str = "block"):
        """Handle block/captcha detection."""
        stats = self.get_stats(category)
        
        if block_type == "captcha":
            stats.captchas_detected += 1
            if stats.captchas_detected >= self.config.captcha_threshold:
                await self.alert(
                    f"*CAPTCHA Flood Detected*\n"
                    f"Category: `{category}`\n"
                    f"Captchas: {stats.captchas_detected}\n"
                    f"Last URL: `{url}`\n\n"
                    f"⚡ Consider rotating proxies or adding delays",
                    AlertLevel.WARNING
                )
                stats.captchas_detected = 0
        else:
            stats.blocks_detected += 1
            if stats.blocks_detected >= self.config.block_threshold:
                await self.alert(
                    f"*IP Block Detected*\n"
                    f"Category: `{category}`\n"
                    f"Blocks: {stats.blocks_detected}\n"
                    f"Last URL: `{url}`\n\n"
                    f"⚡ Proxy rotation triggered",
                    AlertLevel.WARNING
                )
                stats.blocks_detected = 0
    
    async def on_category_complete(self, category: str, items_count: int, duration_secs: float):
        """Report category scrape completion."""
        await self.alert(
            f"*Category Complete*\n"
            f"Category: `{category}`\n"
            f"Items: {items_count}\n"
            f"Duration: {duration_secs/60:.1f} minutes",
            AlertLevel.SUCCESS
        )
    
    async def on_cycle_complete(self, stats_summary: Dict[str, int], total_duration: float):
        """Report full scrape cycle completion."""
        items_summary = "\n".join([f"  • {k}: {v}" for k, v in stats_summary.items()])
        await self.alert(
            f"*Full Cycle Complete*\n"
            f"{items_summary}\n"
            f"Total Duration: {total_duration/3600:.1f} hours",
            AlertLevel.SUCCESS
        )
    
    async def on_startup(self, categories: list):
        """Send startup notification."""
        await self.alert(
            f"*Scraper Started*\n"
            f"Categories: `{', '.join(categories)}`\n"
            f"Environment: `{get_environment().value}`",
            AlertLevel.INFO
        )
    
    async def on_shutdown(self, reason: str = "Manual stop"):
        """Send shutdown notification."""
        # Compile final stats
        total_items = sum(s.items_scraped for s in self.stats.values())
        await self.alert(
            f"*Scraper Stopped*\n"
            f"Reason: {reason}\n"
            f"Total items scraped: {total_items}",
            AlertLevel.INFO
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check and return status."""
        status = {
            "timestamp": datetime.now().isoformat(),
            "environment": get_environment().value,
            "telegram_enabled": self.config.telegram_enabled,
            "email_enabled": self.config.email_enabled,
            "categories": {},
        }
        
        for category, stats in self.stats.items():
            status["categories"][category] = {
                "items_scraped": stats.items_scraped,
                "consecutive_errors": stats.consecutive_errors,
                "blocks_detected": stats.blocks_detected,
                "last_success": stats.last_success_time.isoformat() if stats.last_success_time else None,
            }
        
        return status


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get or create the global alert manager."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


async def cleanup_alerts():
    """Cleanup alert manager resources."""
    global _alert_manager
    if _alert_manager:
        await _alert_manager.close()
        _alert_manager = None


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def alert_info(message: str):
    """Send an info alert."""
    await get_alert_manager().alert(message, AlertLevel.INFO)


async def alert_warning(message: str):
    """Send a warning alert."""
    await get_alert_manager().alert(message, AlertLevel.WARNING)


async def alert_error(message: str):
    """Send an error alert."""
    await get_alert_manager().alert(message, AlertLevel.ERROR)


async def alert_critical(message: str):
    """Send a critical alert."""
    await get_alert_manager().alert(message, AlertLevel.CRITICAL)


if __name__ == "__main__":
    # Test alerts
    async def test():
        manager = get_alert_manager()
        await manager.on_startup(["immobilier", "voiture"])
        await manager.on_scrape_success("immobilier", "https://example.com")
        await manager.on_scrape_error("immobilier", "https://example.com", "Test error")
        health = await manager.health_check()
        print(json.dumps(health, indent=2))
        await cleanup_alerts()
    
    asyncio.run(test())
