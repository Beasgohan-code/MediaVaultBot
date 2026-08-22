#@mediavault
"""Minimal i18n EN / HI with blockquote-friendly strings."""
from __future__ import annotations

STRINGS = {
    "en": {
        "settings_title": "Settings",
        "quota": "Quota",
        "language": "Language",
        "quality": "Default quality",
        "autodel": "Auto-delete (sec)",
        "saved": "Saved.",
        "tos_need": "Accept /tos first.",
        "age_confirm": "This content may be age-restricted. Confirm you are allowed to access it.",
        "broadcast_done": "Broadcast finished.",
        "no_perm": "Admin only.",
        "export_ready": "Your library export:",
        "backup_ready": "Database backup:",
        "retry_ok": "Retry queued.",
        "me_title": "Your stats",
    },
    "hi": {
        "settings_title": "सेटिंग्स",
        "quota": "कोटा",
        "language": "भाषा",
        "quality": "डिफ़ॉल्ट क्वालिटी",
        "autodel": "ऑटो-डिलीट (सेकंड)",
        "saved": "सेव हो गया।",
        "tos_need": "पहले /tos स्वीकार करें।",
        "age_confirm": "यह कंटेंट एज-रेस्ट्रिक्टेड हो सकता है। पुष्टि करें कि आप इसे एक्सेस कर सकते हैं।",
        "broadcast_done": "ब्रॉडकास्ट पूरा।",
        "no_perm": "केवल एडमिन।",
        "export_ready": "आपका लाइब्रेरी एक्सपोर्ट:",
        "backup_ready": "डेटाबेस बैकअप:",
        "retry_ok": "रीट्राई कतार में।",
        "me_title": "आपके आँकड़े",
    },
}


def t(lang: str, key: str) -> str:
    lang = lang if lang in STRINGS else "en"
    return STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))
