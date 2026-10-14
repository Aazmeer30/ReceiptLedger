"""
API subpackage — convenience re-exports.
Import routers from here for a cleaner app.main.
"""
from app.api import analytics, dashboard, health, receipts, review_queue

__all__ = ["health", "receipts", "analytics", "review_queue", "dashboard"]
