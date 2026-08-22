#@mediavault
"""Drive removed — stub so accidental imports never crash the bot."""
import logging
logger = logging.getLogger(__name__)

class _NoDrive:
    available = False
    async def connect(self):
        logger.info("Google Drive disabled (stub)")
    async def search(self, *a, **k):
        return []
    async def list_files(self, *a, **k):
        return [], None
    async def get_file(self, *a, **k):
        return None
    async def download(self, *a, **k):
        raise RuntimeError("Google Drive is disabled")

drive = _NoDrive()
