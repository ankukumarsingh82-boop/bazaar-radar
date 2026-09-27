"""Indian states and union territories, with Google Trends geo codes."""

from __future__ import annotations

# Codes observed in Trends GEO_MAP responses use the ISO 3166-2 IN set
# (IN-TG Telangana, IN-OR Odisha, IN-UT Uttarakhand, IN-DL Delhi).
STATES: list[tuple[str, str]] = [
    ("IN-AP", "Andhra Pradesh"),
    ("IN-AR", "Arunachal Pradesh"),
    ("IN-AS", "Assam"),
    ("IN-BR", "Bihar"),
    ("IN-CT", "Chhattisgarh"),
    ("IN-GA", "Goa"),
    ("IN-GJ", "Gujarat"),
    ("IN-HR", "Haryana"),
    ("IN-HP", "Himachal Pradesh"),
    ("IN-JH", "Jharkhand"),
    ("IN-KA", "Karnataka"),
    ("IN-KL", "Kerala"),
    ("IN-MP", "Madhya Pradesh"),
    ("IN-MH", "Maharashtra"),
    ("IN-MN", "Manipur"),
    ("IN-ML", "Meghalaya"),
    ("IN-MZ", "Mizoram"),
    ("IN-NL", "Nagaland"),
    ("IN-OR", "Odisha"),
    ("IN-PB", "Punjab"),
    ("IN-RJ", "Rajasthan"),
    ("IN-SK", "Sikkim"),
    ("IN-TN", "Tamil Nadu"),
    ("IN-TG", "Telangana"),
    ("IN-TR", "Tripura"),
    ("IN-UP", "Uttar Pradesh"),
    ("IN-UT", "Uttarakhand"),
    ("IN-WB", "West Bengal"),
    ("IN-AN", "Andaman and Nicobar Islands"),
    ("IN-CH", "Chandigarh"),
    ("IN-DL", "Delhi"),
    ("IN-JK", "Jammu and Kashmir"),
    ("IN-LA", "Ladakh"),
    ("IN-LD", "Lakshadweep"),
    ("IN-PY", "Puducherry"),
]

STATE_NAMES = dict(STATES)

CATEGORIES = ["Home & Décor", "Fashion", "Gifting", "Kitchen"]
