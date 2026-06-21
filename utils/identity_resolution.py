import difflib
import re
from typing import Dict, List, Optional

# High-fidelity mapping for major industry players. Values are canonical
# identities used for verification, deduplication, and graph identity.
IDENTITY_MAP = {
    "TSMC": "Taiwan Semiconductor Manufacturing Company",
    "Taiwan Semiconductor": "Taiwan Semiconductor Manufacturing Company",
    "Taiwan Semiconductor Manufacturing Co": "Taiwan Semiconductor Manufacturing Company",
    "Taiwan Semiconductor Manufacturing Co.": "Taiwan Semiconductor Manufacturing Company",
    "TSMC Semiconductor Manufacturing Company Limited": "Taiwan Semiconductor Manufacturing Company",
    "Foxconn": "Hon Hai Precision Industry Co., Ltd.",
    "Foxconn Technology Group": "Hon Hai Precision Industry Co., Ltd.",
    "Hon Hai": "Hon Hai Precision Industry Co., Ltd.",
    "Hon Hai Precision": "Hon Hai Precision Industry Co., Ltd.",
    "Hon Hai Precision Industry": "Hon Hai Precision Industry Co., Ltd.",
    "Hon Hai Precision Industry Co": "Hon Hai Precision Industry Co., Ltd.",
    "Hon Hai Precision Industry Co Ltd": "Hon Hai Precision Industry Co., Ltd.",
    "Hon Hai Precision Industry Co., Ltd.": "Hon Hai Precision Industry Co., Ltd.",
    "Hon Hai Technology Group": "Hon Hai Precision Industry Co., Ltd.",
    "Google": "Alphabet Inc.",
    "Alphabet": "Alphabet Inc.",
    "Facebook": "Meta Platforms Inc.",
    "Meta": "Meta Platforms Inc.",
    "Apple": "Apple Inc.",
    "Apple Inc": "Apple Inc.",
    "Tesla": "Tesla",
    "Tesla Inc": "Tesla",
    "Nvidia": "NVIDIA",
    "NVIDIA Corporation": "NVIDIA",
    "Intel": "Intel",
    "Intel Corporation": "Intel",
    "Samsung": "Samsung Electronics",
    "Samsung Electronics": "Samsung Electronics",
    "Samsung Electronics Co": "Samsung Electronics",
    "Samsung Electronics Co.": "Samsung Electronics",
    "Samsung Electronics Co Ltd": "Samsung Electronics",
    "Samsung Electronics Co., Ltd.": "Samsung Electronics",
    "CATL": "Contemporary Amperex Technology Co. Limited",
    "Contemporary Amperex Technology": "Contemporary Amperex Technology Co. Limited",
    "Contemporary Amperex Technology Co": "Contemporary Amperex Technology Co. Limited",
    "LG Energy": "LG Energy Solution",
    "LGES": "LG Energy Solution",
    "Samsung SDI Co": "Samsung SDI",
    "SK Hynix": "SK hynix",
    "SK hynix": "SK hynix",
    "Hynix": "SK hynix",
    "Micron": "Micron Technology",
    "Micron Technology Inc": "Micron Technology",
    "Pegatron": "Pegatron Corporation",
    "Pegatron Corporation": "Pegatron Corporation",
    "Murata": "Murata Manufacturing",
    "Murata Manufacturing Co": "Murata Manufacturing",
    "Murata Manufacturing Co.": "Murata Manufacturing",
    "Corning": "Corning Inc.",
    "Corning Inc": "Corning Inc.",
    "Corning Inc.": "Corning Inc.",
    "Broadcom": "Broadcom Inc.",
    "Broadcom Inc": "Broadcom Inc.",
    "Broadcom Inc.": "Broadcom Inc.",
    "Panasonic Holdings": "Panasonic",
    "Panasonic Energy": "Panasonic",
    "ASML Holding": "ASML",
    "ASML Holding NV": "ASML",
    "Applied Materials Inc": "Applied Materials",
    "Lam Research Corporation": "Lam Research",
    "Tokyo Electron Limited": "Tokyo Electron",
    "KLA Corporation": "KLA",
    "KLA Corp": "KLA",
    "Carl Zeiss SMT": "Carl Zeiss SMT",
    "Zeiss": "Carl Zeiss SMT",
    "Qualcomm Inc": "Qualcomm",
    "Qualcomm Incorporated": "Qualcomm",
    "Advanced Micro Devices": "AMD",
    "Advanced Micro Devices Inc": "AMD",
    "AMD": "AMD",
    "GlobalFoundries Inc": "GlobalFoundries",
    "GlobalFoundries": "GlobalFoundries",
    "ASE Technology": "ASE Technology",
    "ASE": "ASE Technology",
    "ASE Technology Holding": "ASE Technology",
    "ASE Technology Holding Co": "ASE Technology",
    "Amkor": "Amkor Technology",
    "Amkor Technology": "Amkor Technology",
    "Compal": "Compal Electronics",
    "Compal Electronics": "Compal Electronics",
    "Compal Electronics Inc": "Compal Electronics",
    "Quanta": "Quanta Computer",
    "Quanta Computer": "Quanta Computer",
    "Quanta Computer Inc": "Quanta Computer",
    "Wistron": "Wistron",
    "Wistron Corporation": "Wistron",
    "Inventec": "Inventec",
    "Inventec Corporation": "Inventec",
    "Marvell": "Marvell Technology, Inc.",
    "Marvell Technology": "Marvell Technology, Inc.",
    "Marvell Technology Group": "Marvell Technology, Inc.",
    "Marvell Technology Inc": "Marvell Technology, Inc.",
    "Marvell Technology, Inc.": "Marvell Technology, Inc.",
    "Sony Semiconductor": "Sony Semiconductor Solutions",
    "Sony Semiconductor Solutions": "Sony Semiconductor Solutions",
    "Sony Semiconductor Solutions Corporation": "Sony Semiconductor Solutions",
    "Taiwan Semiconductor Manufacturing Company": "Taiwan Semiconductor Manufacturing Company",
    "Taiwan Semiconductor Manufacturing Company Limited": "Taiwan Semiconductor Manufacturing Company",
    "Dell": "Dell Technologies",
    "Dell Inc": "Dell Technologies",
    "Dell Technologies": "Dell Technologies",
}

DISPLAY_NAMES = {
    "Taiwan Semiconductor Manufacturing Company": "TSMC",
    "Hon Hai Precision Industry Co., Ltd.": "Hon Hai Precision Industry",
    "Pegatron Corporation": "Pegatron",
    "Samsung Electronics": "Samsung Electronics",
    "SK hynix": "SK hynix",
    "Broadcom Inc.": "Broadcom",
    "Compal Electronics": "Compal Electronics",
    "Marvell Technology, Inc.": "Marvell Technology",
    "Corning Inc.": "Corning",
    "Murata Manufacturing": "Murata Manufacturing",
    "Sony Semiconductor Solutions": "Sony Semiconductor Solutions",
}

# Common corporate suffixes for normalization
CORPORATE_SUFFIXES = [
    r"\bInc\.?\b", r"\bLtd\.?\b", r"\bCorp\.?\b", r"\bGroup\b", 
    r"\bCo\.?\b", r"\bPLC\b", r"\bCorporation\b", r"\bLimited\b",
    r"\bS\.A\.?\b", r"\bA\.G\.?\b", r"\bN\.V\.?\b", r"\bB\.V\.?\b"
]


def compact_key(value: str) -> str:
    """Case-insensitive comparison key shared across identity users."""
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _collapse_repeated_prefixes(text: str) -> str:
    words = text.split()
    if len(words) < 2:
        return text

    max_prefix_words = min(4, len(words) // 2)
    for prefix_len in range(max_prefix_words, 0, -1):
        prefix = " ".join(words[:prefix_len]).lower().strip(".,")
        repeated = " ".join(words[prefix_len : prefix_len * 2]).lower().strip(".,")
        if prefix and prefix == repeated:
            return " ".join(words[prefix_len:])

    deduped = []
    for word in words:
        if not deduped or deduped[-1].lower().strip(".,") != word.lower().strip(".,"):
            deduped.append(word)
    return " ".join(deduped)

def normalize_name(name: str) -> str:
    """Removes common corporate suffixes and standardizes casing/spacing."""
    if not name:
        return ""
    
    # 1. Basic cleaning
    norm = name.strip()
    norm = re.sub(r"\s+", " ", norm)
    norm = re.sub(r"[,.]+$", "", norm).strip()
    norm = _collapse_repeated_prefixes(norm)

    # 2. Remove suffixes
    for suffix in CORPORATE_SUFFIXES:
        norm = re.sub(suffix, "", norm, flags=re.IGNORECASE).strip()

    # 3. Standardize whitespace and remove trailing punctuation
    norm = re.sub(r"\s+", " ", norm)
    norm = re.sub(r"[,.]+$", "", norm).strip()
    norm = _collapse_repeated_prefixes(norm)
    
    return norm


def _suffixless_variant(name: str) -> str:
    variant = normalize_name(name)
    variant = re.sub(r"\s+", " ", variant).strip()
    return variant


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    deduped = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", (value or "").strip())
        if not cleaned:
            continue
        key = compact_key(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    return deduped

def detect_abbreviation(short: str, long: str) -> bool:
    """Checks if 'short' could be an abbreviation of 'long' (e.g., TSMC for Taiwan Semi...)."""
    short = short.upper().replace(".", "")
    long_words = [w for w in re.split(r"[\s-]+", long) if w]
    
    if not long_words or not short:
        return False
        
    # Pattern 1: Initials (TSMC -> Taiwan Semiconductor Manufacturing Company)
    initials = "".join([w[0].upper() for w in long_words if w[0].isalpha()])
    if short == initials:
        return True
        
    return False

class IdentityResolver:
    """Resolves raw supplier names to canonical entities."""
    
    def __init__(self, mapping: Optional[Dict[str, str]] = None):
        self.mapping = mapping or IDENTITY_MAP
        self._compact_mapping = self._build_compact_mapping()
        self._known_canonicals = set(self.mapping.values())

    def _build_compact_mapping(self) -> Dict[str, str]:
        compact_mapping: Dict[str, str] = {}
        for alias, canonical in self.mapping.items():
            compact_mapping[compact_key(alias)] = canonical
            compact_mapping[compact_key(normalize_name(alias))] = canonical
            compact_mapping[compact_key(canonical)] = canonical
            compact_mapping[compact_key(normalize_name(canonical))] = canonical
        return {key: value for key, value in compact_mapping.items() if key}
        
    def resolve(self, name: str) -> str:
        """
        Main entry point for identity resolution.
        Uses mapping, normalization, abbreviation detection, and fuzzy matching.
        """
        if not name:
            return name

        clean_name = re.sub(r"\s+", " ", name.strip())

        # 1. Direct and normalized mapping using compact keys.
        for candidate in (clean_name, normalize_name(clean_name), _suffixless_variant(clean_name)):
            canonical = self._compact_mapping.get(compact_key(candidate))
            if canonical:
                return canonical
        
        # 2. Abbreviation Detection
        for key, canonical in self.mapping.items():
            if detect_abbreviation(clean_name, canonical) or detect_abbreviation(clean_name, key):
                return canonical

        # 3. Fuzzy Matching (if no direct hit)
        matches = difflib.get_close_matches(
            compact_key(clean_name),
            list(self._compact_mapping.keys()),
            n=1,
            cutoff=0.88,
        )
        if matches:
            return self._compact_mapping[matches[0]]
            
        # If no match found, return the name itself as the best guess
        return clean_name

    def display_name(self, name: str) -> str:
        """Return a concise readable label for UI/report display."""
        canonical = self.resolve(name)
        return DISPLAY_NAMES.get(canonical, canonical)

    def is_known_entity(self, name: str) -> bool:
        if not name:
            return False
        canonical = self.resolve(name)
        return (
            compact_key(name) in self._compact_mapping
            or compact_key(canonical) in self._compact_mapping
            or canonical in self._known_canonicals
        )

    def aliases_for(self, name: str) -> List[str]:
        canonical = self.resolve(name)
        aliases = [name, canonical, DISPLAY_NAMES.get(canonical, "")]
        canonical_key = compact_key(canonical)
        for alias, mapped_canonical in self.mapping.items():
            if compact_key(mapped_canonical) == canonical_key:
                aliases.append(alias)

        suffixless = _suffixless_variant(canonical)
        if suffixless and suffixless != canonical:
            aliases.append(suffixless)

        if canonical.endswith("Inc."):
            aliases.append(canonical[:-1])
        if canonical.endswith(", Inc."):
            aliases.append(canonical.replace(", Inc.", ""))
            aliases.append(canonical.replace(", Inc.", " Inc"))
        if canonical.endswith("Co., Ltd."):
            aliases.append(canonical.replace("Co., Ltd.", "Co Ltd"))
            aliases.append(canonical.replace(" Co., Ltd.", ""))

        return _dedupe_preserve_order(aliases)

    def wikipedia_search_candidates(self, name: str) -> List[str]:
        """Candidate titles to try before declaring Wikipedia lookup failure."""
        candidates: List[str] = []
        for alias in self.aliases_for(name):
            candidates.append(alias)
            candidates.append(alias.replace(",", ""))
            if alias.endswith("."):
                candidates.append(alias[:-1])
        return _dedupe_preserve_order(candidates)

    def term_variants(self, name: str) -> List[str]:
        variants = []
        for alias in self.aliases_for(name):
            variants.append(alias)
            variants.append(compact_key(alias))
        canonical = self.resolve(name)
        words = canonical.split()
        if len(words) >= 2:
            variants.append(" ".join(words[:2]))
        if len(words) >= 3:
            variants.append(" ".join(words[:3]))
        return _dedupe_preserve_order(variants)

# Singleton instance
resolver = IdentityResolver()
