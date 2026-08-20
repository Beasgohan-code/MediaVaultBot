#@mediavault
"""Simple in-memory state for active downloads / browse sessions."""
from __future__ import annotations

from typing import Dict, Any

# user_id -> current browse folder_id
browse_state: Dict[int, str] = {}

# user_id -> last search query
search_state: Dict[int, str] = {}

# active download tasks (for cancel support later)
active_downloads: Dict[int, Any] = {}
