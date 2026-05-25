import re


EMOJI_PATTERN = re.compile(
    "["
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\u2600-\u27bf"
    "]+",
    flags=re.UNICODE,
)


NO_EMOJI_RULE = (
    "Never use emojis, emoticons, decorative symbols, or pictograms. "
    "Write in clear professional prose only."
)


def strip_emojis(text: str) -> str:
    return EMOJI_PATTERN.sub("", text).strip()


def has_emoji(text: str) -> bool:
    return bool(EMOJI_PATTERN.search(text))
