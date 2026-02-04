"""
Scheduler Service
Background jobs for auth refresh and maintenance tasks
"""

import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("adg-scheduler")


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
        logger.error(f"🚨 CRITICAL: Auth has failed {self.consecutive_failures} times!")
        logger.error(f"🚨 Please check authentication")
        # TODO: Add Slack/Email notification here


class SchedulerService:
    """
    Background scheduler for maintenance tasks.
    
    Handles:
    - NotebookLM session keep-alive
    - Token refresh
    - Health monitoring
    """
    
    def __init__(self):
        self._scheduler: Optional[BackgroundScheduler] = None
        self._health_checker = AuthHealthChecker()
    
    @property
    def health_checker(self) -> AuthHealthChecker:
        return self._health_checker
    
    def refresh_notebooklm_auth(self):
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
                self._health_checker.update_status(False, "No cached tokens found")
                return
            
            client = NotebookLMClient(
                cookies=cached.cookies,
                csrf_token=cached.csrf_token,
                session_id=cached.session_id
            )
            
            notebooks = client.list_notebooks()
            
            if notebooks is not None:
                self._health_checker.update_status(True)
                logger.info(f"📓 Found {len(notebooks)} notebooks - session is alive")
            else:
                self._health_checker.update_status(False, "list_notebooks returned None")
                
        except Exception as e:
            error_msg = str(e)
            self._health_checker.update_status(False, error_msg)
            
            if "401" in error_msg or "Unauthorized" in error_msg or "RPC Error 16" in error_msg:
                logger.error("🔑 Session expired! Manual re-auth required.")
    
    def start(self) -> BackgroundScheduler:
        """Start the background scheduler with auto token refresh"""
        if self._scheduler is not None:
            return self._scheduler
        
        self._scheduler = BackgroundScheduler()
        
        # Add token refresh job
        self._scheduler.add_job(
            self.refresh_notebooklm_auth,
            trigger=IntervalTrigger(minutes=settings.AUTH_REFRESH_INTERVAL_MINUTES),
            id="token_refresh",
            name="NotebookLM Token Auto-Refresh",
            replace_existing=True
        )
        
        self._scheduler.start()
        logger.info(f"⏰ Scheduler started - auto refresh every {settings.AUTH_REFRESH_INTERVAL_MINUTES} minutes")
        
        # Run initial check
        self.refresh_notebooklm_auth()
        
        return self._scheduler
    
    def stop(self):
        """Stop the scheduler"""
        if self._scheduler:
            self._scheduler.shutdown()
            self._scheduler = None
            logger.info("⏹️ Scheduler stopped")


# Singleton instance
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    """Get or create scheduler service singleton"""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
