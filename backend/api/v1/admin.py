"""
Admin API - Re-export Module
Backwards compatibility shim. All admin endpoints are now in:
  - admin_users.py (user management + guards)
  - admin_departments.py (department listing)
  - admin_roles.py (roles + permission types)
  - admin_folders.py (folder management + permissions + sync)

This file only re-exports guards so that other modules
(rag.py, health.py, activity_logs.py) can still import from here.
"""

# Re-export guards for backwards compatibility
from backend.api.v1.admin_users import (  # noqa: F401
    require_admin,
    require_admin_or_manager,
    _ensure_view_permission_type,
)
