"""
Approval Workflow — Re-export Module
Backwards compatibility shim. All approval endpoints are now in:
  - approval_submit.py (upload/update/delete submission)
  - approval_queries.py (pending/history/my-requests/preview + guard)
  - approval_review.py (approve/reject/batch operations)
"""

# Re-export for backwards compatibility
from backend.api.v1.approval_submit import (  # noqa: F401
    _get_user_department_id,
    _notify_department_approvers,
)
from backend.api.v1.approval_queries import require_approver  # noqa: F401
