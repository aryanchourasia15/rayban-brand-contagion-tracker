"""
Ray-Ban Customer Trust Intelligence
Heuristic Rule-Based Relevance Classifier

Treat classification as a heuristic indicator for research triage,
NOT as validated AI or LLM output.
All records are preserved in the database regardless of classification.
"""

from typing import Optional

from src.config import VALID_RELEVANCE_FLAGS

# Heuristic keywords for privacy, recording, and surveillance controversies
PRIVACY_CONTROVERSY_TERMS = (
    "privacy",
    "surveillance",
    "recording",
    "recordings",
    "camera",
    "cameras",
    "facial recognition",
    "face recognition",
    "spy",
    "spying",
    "secret recording",
    "covert",
    "creepy",
    "data collection",
    "consent",
    "wiretap",
    "wiretapping",
    "tracking",
    "banned",
    "controversy",
    "controversial",
    "doxxing",
    "doxx",
    "stalking",
    "stalk",
    "backlash",
    "investigation",
    "probe",
)

# Heuristic keywords for Ray-Ban Meta and smart glasses product scope
PRODUCT_TERMS = (
    "ray-ban meta",
    "ray ban meta",
    "rayban meta",
    "meta smart glasses",
    "meta glasses",
    "smart glasses",
    "smartglasses",
    "stories",
    "wayfarer",
    "headliner",
    "meta ai glasses",
    "wearable camera",
)


def classify_relevance(
    text: Optional[str] = None,
    title: Optional[str] = None,
    url: Optional[str] = None,
) -> str:
    """
    Classify a record into one of three heuristic relevance tiers:
    - 'relevant': Direct intersection of Ray-Ban Meta / smart glasses and privacy / recording controversies.
    - 'contextual': Mentions Ray-Ban Meta / smart glasses or privacy/wearables in a general tech, market, or review context.
    - 'irrelevant': Tangential mentions, generic gift guides, unrelated products, or off-topic items.

    Design Notes:
    - This is a lightweight keyword heuristic, NOT validated AI or LLM output.
    - Preserves all records regardless of classification: records are never discarded
      or filtered out on the basis of their relevance flag.
    """
    parts = []
    for val in (title, text, url):
        if val is not None:
            val_clean = str(val).strip().lower()
            if val_clean:
                parts.append(val_clean)

    combined = " ".join(parts)
    if not combined:
        return "irrelevant"

    has_product = any(term in combined for term in PRODUCT_TERMS)
    has_privacy = any(term in combined for term in PRIVACY_CONTROVERSY_TERMS)

    if has_product and has_privacy:
        return "relevant"
    if has_product or has_privacy:
        return "contextual"
    return "irrelevant"
