import re
import unicodedata


def generate_name_id(name: str) -> str:
    """Stable unique logical id from a display name. Not typed by the user."""
    if not name:
        return ""

    decomposed = unicodedata.normalize("NFD", name)
    without_accents = "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    )
    lowered = without_accents.lower()
    underscored = re.sub(r"[^a-z0-9]+", "_", lowered)
    collapsed = re.sub(r"_+", "_", underscored)
    return collapsed.strip("_")
