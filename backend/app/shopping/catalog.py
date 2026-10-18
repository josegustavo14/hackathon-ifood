"""Conservative catalog terms for prepared fresh produce.

The recipe keeps its original ingredient name; only catalog lookup uses this term.
"""

import re
import unicodedata


_PRODUCE = (
    "abobrinha", "abóbora", "alface", "alho", "alho-poró", "azeitonas", "batata",
    "berinjela", "beterraba", "brócolis", "cenoura", "cebola", "chuchu",
    "couve", "couve-flor", "espinafre", "mandioca", "pepino", "pimentão",
    "quiabo", "repolho", "tomate", "vagem",
)
_PREPARATION = re.compile(
    r"(?:,?\s+(?:fatiad[oa]s?|picad[oa]s?|cortad[oa]s?"
    r"(?:\s+em\s+(?:cubos|rodelas|tiras|fatias))?|descascad[oa]s?|"
    r"lavad[oa]s?))$",
    re.IGNORECASE,
)
_CUT = re.compile(r"(?:,?\s+em\s+(?:cubos|rodelas|tiras|fatias(?:\s+finas)?))$", re.IGNORECASE)
_CATALOG_ALIASES = {
    "azeitonas verdes": "azeitona verde",
    "azeitonas pretas": "azeitona preta",
    "molho de tomate pronto": "molho de tomate",
}


def _plain(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(char))


def catalog_ingredient_name(name: str) -> str:
    """Drop explicit preparation words from vegetables, without changing product types."""
    original = " ".join(name.split()).strip(" ,")
    plain = _plain(original)
    if plain in _CATALOG_ALIASES:
        return _CATALOG_ALIASES[plain]
    if not any(plain == produce or plain.startswith((produce + " ", produce + ","))
               for produce in _PRODUCE_NORMALIZED):
        return original
    result = original
    while True:
        shortened = _CUT.sub("", _PREPARATION.sub("", result)).strip(" ,")
        if shortened == result:
            return _CATALOG_ALIASES.get(_plain(result), result)
        result = shortened


_PRODUCE_NORMALIZED = tuple(_plain(name) for name in _PRODUCE)
