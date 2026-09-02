"""Stage name <-> text key mapping for deals/pipelines."""
from typing import Optional


def stage_key_from_name(name: Optional[str]) -> Optional[str]:
    """Map a stage display name (e.g. 'Lead', 'Ganho') to its text key."""
    if not name:
        return None
    n = name.strip().lower()
    aliases = {"ganho": "closed_won", "perdido": "closed_lost"}
    return aliases.get(n, n)


def stage_name_from_key(key: Optional[str]) -> Optional[str]:
    """Map a text key (e.g. 'closed_won') back to a canonical display name."""
    if not key:
        return None
    aliases = {"closed_won": "Ganho", "closed_lost": "Perdido"}
    return aliases.get(key, key.replace("_", " ").title())