"""
Auto Re-auth Scheduler for NotebookLM
Pings NotebookLM every 30 minutes to keep session alive
"""

import os
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notebooklm-scheduler")

# Configuration
AUTH_REFRESH_INTERVAL_MINUTES = int(os.getenv("AUTH_REFRESH_INTERVAL_MINUTES", "30"))


class AuthHealthChecker:
    """Tracks authentication health status"""
    
    def __init__(self):
        self.last_refresh_time: Optional[str] = None
        self.last_status: str = "unknown"
        self.consecutive_failures: int = 0
    
    def update_status(self, success: bool, message: str = ""):
        """Update health status after refresh attempt"""
        self.last_refresh_time = datetime.now().isoformat()
        
        if success:
            self.last_status = "healthy"
            self.consecutive_failures = 0
            logger.info(f"✅ Auth refresh successful at {self.last_refresh_time}")
        else:
            self.last_status = "unhealthy"
            self.consecutive_failures += 1
            logger.warning(f"⚠️ Auth refresh failed: {message} (failures: {self.consecutive_failures})")
            
            # Alert after 3 consecutive failures
            if self.consecutive_failures >= 3:
                self._send_alert(message)
    
    def _send_alert(self, message: str):
        """Send alert on repeated failures - extend for Slack/Email integration"""
        logger.error(f"🚨 CRITICAL: NotebookLM auth has failed {self.consecutive_failures} times!")
        logger.error(f"🚨 Please run 'notebooklm-mcp-auth' to re-authenticate")
        # TODO: Add Slack/Email notification here


# Global health checker instance
_health_checker = AuthHealthChecker()


def get_health_checker() -> AuthHealthChecker:
    """Get global health checker instance"""
    return _health_checker


def refresh_auth():
    """
    Refresh NotebookLM authentication by pinging the service.
    This keeps the session cookies alive.
    """
    from notebooklm_mcp.api_client import NotebookLMClient
    from notebooklm_mcp.auth import load_cached_tokens
    
    logger.info(f"🔄 Starting auth refresh at {datetime.now().isoformat()}")
    
    try:
        cached = load_cached_tokens()
        if not cached:
            _health_checker.update_status(False, "No cached tokens found")
            return
        
        # Create client and make a lightweight request
        client = NotebookLMClient(
            cookies=cached.cookies,
            csrf_token=cached.csrf_token,
            session_id=cached.session_id
        )
        
        # List notebooks as a health check (lightweight operation)
        notebooks = client.list_notebooks()
        
        if notebooks is not None:
            _health_checker.update_status(True)
            logger.info(f"📓 Found {len(notebooks)} notebooks - session is alive")
        else:
            _health_checker.update_status(False, "list_notebooks returned None")
            
    except Exception as e:
        error_msg = str(e)
        _health_checker.update_status(False, error_msg)
        
        # Check for specific auth errors
        if "401" in error_msg or "Unauthorized" in error_msg or "RPC Error 16" in error_msg:
            logger.error("🔑 Session expired! Attempting headless re-auth...")
            # Try headless re-auth automatically
            run_headless_token_refresh()


def run_headless_token_refresh():
    """
    Attempt to refresh tokens using headless Chrome.
    This uses the saved Chrome profile from initial manual auth.
    """
    try:
        from notebooklm_mcp.auth_cli import run_headless_auth
        
        logger.info("🔄 Attempting headless token refresh...")
        
        # Run headless auth on a different port to avoid conflicts
        result = run_headless_auth(port=9223, timeout=60)
        
        if result:
            _health_checker.update_status(True)
            logger.info("✅ Headless token refresh successful! New tokens cached.")
            return True
        else:
            _health_checker.update_status(False, "Headless auth returned None")
            logger.warning("⚠️ Headless auth failed - may need manual re-auth")
            return False
            
    except Exception as e:
        error_msg = str(e)
        _health_checker.update_status(False, f"Headless auth error: {error_msg}")
        logger.error(f"❌ Headless token refresh failed: {error_msg}")
        return False


def refresh_tokens_job():
    """
    Scheduled job that attempts to refresh tokens.
    First checks if current tokens work, then refreshes if needed.
    """
    from notebooklm_mcp.auth import load_cached_tokens
    
    logger.info(f"⏰ Scheduled token refresh at {datetime.now().isoformat()}")
    
    try:
        cached = load_cached_tokens()
        if not cached:
            logger.warning("No cached tokens - attempting headless refresh")
            run_headless_token_refresh()
            return
        
        # Check if tokens are still valid with a quick ping
        from notebooklm_mcp.api_client import NotebookLMClient
        
        client = NotebookLMClient(
            cookies=cached.cookies,
            csrf_token=cached.csrf_token,
            session_id=cached.session_id
        )
        
        notebooks = client.list_notebooks()
        
        if notebooks is not None:
            logger.info(f"✅ Current tokens still valid - {len(notebooks)} notebooks found")
            _health_checker.update_status(True)
        else:
            logger.warning("⚠️ Tokens may be expired - refreshing...")
            run_headless_token_refresh()
            
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"⚠️ Token check failed: {error_msg}")
        
        # If auth error, try headless refresh
        if "401" in error_msg or "Unauthorized" in error_msg or "RPC Error" in error_msg:
            run_headless_token_refresh()
        else:
            _health_checker.update_status(False, error_msg)


def start_scheduler():
    """Start the background scheduler with auto token refresh"""
    scheduler = BackgroundScheduler()
    
    # Add token refresh job - checks and refreshes tokens automatically
    scheduler.add_job(
        refresh_tokens_job,
        trigger=IntervalTrigger(minutes=AUTH_REFRESH_INTERVAL_MINUTES),
        id="token_refresh",
        name="NotebookLM Token Auto-Refresh",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info(f"⏰ Scheduler started - auto token refresh every {AUTH_REFRESH_INTERVAL_MINUTES} minutes")
    
    # Run initial token check
    refresh_tokens_job()
    
    return scheduler


if __name__ == "__main__":
    # Test the scheduler standalone
    import time
    
    print("Testing auth refresh scheduler...")
    scheduler = start_scheduler()
    
    try:
        while True:
            time.sleep(60)
            print(f"Health: {_health_checker.last_status}, Last check: {_health_checker.last_refresh_time}")
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("Scheduler stopped")
