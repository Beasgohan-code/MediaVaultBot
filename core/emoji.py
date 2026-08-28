#@mediavault
"""Telegram custom (premium) emoji helpers — HTML tg-emoji tags."""
from __future__ import annotations

# User-supplied custom emoji document IDs
E = {
    "tag": "6213102872964373588",
    "money": "6212758407997300195",
    "star": "6212881347141181453",
    "shield": "6212888532621467632",
    "star2": "6212872632652537745",
    "four": "6215084107018280981",
    "one": "6215384338117173007",
    "snow": "6213147188436934178",
    "hot": "6213236463627148940",
    "ghost": "6215238098775711325",
    "plane": "6215519058356346579",
    "star3": "6213036047568215324",
    "star4": "6213108619630616849",
    "up": "6212943680001548423",
    "strong": "6212968582221930176",
    "crown": "6213064845323936748",
    "tree": "6213268830500693640",
    "pin": "6213185873207370614",
    "gift": "6213142171915132223",
    "cheers": "6213050328334474612",
    "glow": "6214971316882120764",
    "broken": "6215453006054301341",
    "down": "6213101004653600827",
    "diamond_blue": "6213265381641952794",
    "diamond_orange": "6213065064367267416",
    "diamond_blue2": "6215140259420708168",
    "brown": "6213044143581569191",
    "orange2": "6212982356182049311",
    "green": "6212751553229496466",
    "white": "6212972890074127433",
    "flower": "6213270037386501707",
    "flower2": "6213064845323936747",
    "fire": "6213087690254984403",
    "sparkle": "6215181302128189616",
    "candy": "6212862878781808749",
    "dislike": "6215355810944393322",
    "check": "6212749607609310928",
    "alert": "6213218197131238608",
    "block": "6215437965078831526",
    "red": "6214970556672909067",
    "love": "6215088724108124392",
    "party": "6212760113099317592",
    "mind": "6213101112027784667",
    "ghost2": "6213097268032053230",
    "pumpkin": "6213078314341375822",
    "tree2": "6215161339120197379",
    "moai": "6212892256358118824",
    "coin": "6213059592578932964",
    "crystal": "6213160567260061243",
    "wind": "6212940488840847051",
    "letter": "6212837985151361529",
    "heart": "6212880041471123172",
    "web": "6215009975882751628",
    "alert2": "6215075830616301088",
    "celebrate": "6213198676504878714",
    "bookmark": "6213221250852987064",
    "snow2": "6212718237168180631",
    "rain": "6212824769536992332",
    "red2": "6215331389760348345",
    "gem": "6215348101478097302",
}


def ce(key: str, fallback: str = "•") -> str:
    """HTML custom emoji tag for parse_mode=HTML."""
    eid = E.get(key)
    if not eid:
        return fallback
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'


def thinking_frames() -> list[str]:
    """Animated status lines while downloading."""
    a = ce
    return [
        f"{a('mind', '🧠')} <b>Thinking</b> — analyzing link…",
        f"{a('crystal', '🔮')} Resolving formats…",
        f"{a('sparkle', '✨')} Preparing download…",
        f"{a('fire', '🔥')} Fetching media…",
        f"{a('plane', '✈️')} Almost there…",
        f"{a('gem', '💎')} Finalizing…",
    ]


def progress_header() -> str:
    return f"{ce('fire', '🔥')} {ce('sparkle', '✨')}"


def ok() -> str:
    return ce("check", "✅")


def bad() -> str:
    return ce("block", "🚫")


def warn() -> str:
    return ce("alert", "🚨")


def star() -> str:
    return ce("star", "⭐")


def crown() -> str:
    return ce("crown", "👑")


def fire() -> str:
    return ce("fire", "🔥")
