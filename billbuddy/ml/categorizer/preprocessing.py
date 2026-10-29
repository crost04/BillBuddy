"""Data preparation: turn a free-text description into clean text for the model."""

import re

# Words that say nothing about the category ("Rewe Kartenzahlung" means "Rewe")
NOISE_WORDS = {"kartenzahlung", "karte", "ec", "zahlung", "einkauf", "filiale", "gmbh", "co", "kg", "danke"}


def clean_description(text: str) -> str:
    """'REWE Markt 34,50 Kartenzahlung' -> 'rewe markt'

    Lower case (people write "REWE", "Rewe" and "rewe"), no digits (amounts and
    branch numbers change every time) and no punctuation or noise words.
    """
    text = text.lower()
    text = re.sub(r"[^a-zäöüß&]+", " ", text)
    words = [w for w in text.split() if len(w) > 1 and w not in NOISE_WORDS]
    return " ".join(words)
