import re
import difflib
from typing import Optional, List, Dict

# High-fidelity mapping for major industry players
IDENTITY_MAP = {
    "TSMC": "Taiwan Semiconductor Manufacturing Company",
    "Taiwan Semiconductor": "Taiwan Semiconductor Manufacturing Company",
    "Taiwan Semiconductor Manufacturing Co": "Taiwan Semiconductor Manufacturing Company",
    "TSMC Semiconductor Manufacturing Company Limited": "Taiwan Semiconductor Manufacturing Company",
    "Foxconn": "Hon Hai Precision Industry",
    "Hon Hai": "Hon Hai Precision Industry",
    "Hon Hai Precision": "Hon Hai Precision Industry",
    "Google": "Alphabet Inc.",
    "Alphabet": "Alphabet Inc.",
    "Facebook": "Meta Platforms Inc.",
    "Meta": "Meta Platforms Inc.",
    "Apple": "Apple Inc.",
    "Samsung": "Samsung Electronics",
}

# Common corporate suffixes for normalization
CORPORATE_SUFFIXES = [
    r"\bInc\.?\b", r"\bLtd\.?\b", r"\bCorp\.?\b", r"\bGroup\b", 
    r"\bCo\.?\b", r"\bPLC\b", r"\bCorporation\b", r"\bLimited\b",
    r"\bS\.A\.?\b", r"\bA\.G\.?\b", r"\bN\.V\.?\b", r"\bB\.V\.?\b"
]

def normalize_name(name: str) -> str:
    """Removes common corporate suffixes and standardizes casing/spacing."""
    if not name:
        return ""
    
    # 1. Basic cleaning
    norm = name.strip()
    
    # 2. Remove suffixes
    for suffix in CORPORATE_SUFFIXES:
        norm = re.sub(suffix, "", norm, flags=re.IGNORECASE).strip()
    
    # 3. Standardize whitespace and remove trailing punctuation
    norm = re.sub(r"\s+", " ", norm)
    norm = re.sub(r"[,.]+$", "", norm).strip()
    
    return norm

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
        
    def resolve(self, name: str) -> str:
        """
        Main entry point for identity resolution.
        Uses mapping, normalization, abbreviation detection, and fuzzy matching.
        """
        if not name:
            return name
            
        # 1. Direct Mapping (Case-insensitive)
        for key, canonical in self.mapping.items():
            if name.lower() == key.lower():
                return canonical
                
        # 2. Normalize and check mapping again
        norm_name = normalize_name(name)
        for key, canonical in self.mapping.items():
            if norm_name.lower() == normalize_name(key).lower():
                return canonical
        
        # 3. Abbreviation Detection
        for key, canonical in self.mapping.items():
            if detect_abbreviation(name, canonical) or detect_abbreviation(name, key):
                return canonical

        # 4. Fuzzy Matching (if no direct hit)
        matches = difflib.get_close_matches(name, self.mapping.keys(), n=1, cutoff=0.8)
        if matches:
            return self.mapping[matches[0]]
            
        # If no match found, return the name itself as the best guess
        return name

# Singleton instance
resolver = IdentityResolver()
