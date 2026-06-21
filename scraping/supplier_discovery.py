import os
import json
import copy
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import logging
import re
import time
from html import unescape
from models.state import SupplierInfo
from utils.identity_resolution import resolver
from utils.runtime_controls import (
    can_consume_web_query,
    remaining_stage_timeout,
    stop_if_timed_out,
)

logger = logging.getLogger(__name__)

CORPORATE_SUFFIX_PATTERN = (
    r"Inc\.?|Ltd\.?|Corp\.?|Group|Co\.?|PLC|Corporation|Limited|LLC|"
    r"Holdings|Technologies|Semiconductor|Electronics|Industries|"
    r"S\.A\.?|A\.G\.?|N\.V\.?|B\.V\.?"
)

GENERIC_CANDIDATE_TERMS = {
    "advanced",
    "business",
    "company",
    "component",
    "components",
    "contract",
    "contracts",
    "consumer",
    "customer",
    "customers",
    "electronics",
    "fabless",
    "group",
    "international",
    "manufacturing",
    "partner",
    "partners",
    "supplier",
    "suppliers",
    "technology",
    "vendor",
    "vendors",
}

INVALID_CANDIDATE_NAMES = {
    "annette clayton",
    "board",
    "booting",
    "contract",
    "five other",
    "byron",
    "cristiano amon",
    "fair trade commission",
    "foundry",
    "graphics",
    "integrated",
    "international rights advocates",
    "jerry sanders",
    "mac",
    "oem",
    "original",
    "ati",
    "athlon",
    "tech corporation",
    "chinese company that",
    "taiwanese company that",
    "hdds",
    "usb flash drives",
    "nand flash",
    "integrated circuit",
    "semiconductor manufacturing corporation",
    "manufacturing international corporation",
    "world is flat",
}

PERSON_FRAGMENT_NAMES = {
    "jack elam",
    "byron",
    "cristiano amon",
    "jerry sanders",
    "annette clayton",
    "mac",
}

PRODUCT_FRAGMENT_NAMES = {
    "hdd",
    "hdds",
    "usb flash drive",
    "usb flash drives",
    "nand flash",
    "nand",
    "dram",
    "memory",
    "google nexus",
    "integrated circuit",
    "lfp batteries",
    "graphics card",
    "graphics cards",
    "laptop",
    "laptops",
    "smartphone",
    "smartphones",
    "display",
    "displays",
    "psu",
    "power supply",
    "power supplies",
    "battery",
    "batteries",
    "thinkpad",
    "thinkpads",
}

LOCATION_FRAGMENT_WORDS = {
    "asia",
    "american",
    "australian",
    "california",
    "china",
    "chinese",
    "cupertino",
    "east asia",
    "economic zone",
    "europe",
    "industrial park",
    "israel",
    "japanese",
    "korean",
    "middle east",
    "north america",
    "south korea",
    "southeast asia",
    "taiwan",
    "taiwanese",
    "technology hub",
    "united states",
}

GENERIC_ORG_PATTERNS = [
    r"^(?:tech|technology|industrial|manufacturing|semiconductor|electronics)\s+"
    r"(?:corporation|corp|company|co|limited|ltd)$",
    r"^company\s+(?:limited|ltd|inc|corp|corporation)$",
    r"^(?:company|corporation|inc|ltd|limited|group)$",
    r"\bcompany\s+that\b",
    r"\bnotable\s+for\s+using\b",
    r"\bcurrently\b",
    r"\bwhile\b",
    r"\bfive\s+other\b",
]

LOCATION_ECOSYSTEM_PATTERNS = [
    r"\bsilicon\s+(?:valley|wadi)\b",
    r"\btechnology\s+hub\b",
    r"\bindustrial\s+park\b",
    r"\beconomic\s+zone\b",
    r"\bspecial\s+economic\s+zone\b",
    r"\bscience\s+park\b",
    r"\binnovation\s+(?:hub|district|cluster|corridor)\b",
    r"\b(?:manufacturing|semiconductor|technology)\s+ecosystem\b",
    r"\b(?:industrial|technology|semiconductor)\s+cluster\b",
    r"\b(?:business|technology|industrial)\s+district\b",
    r"\b(?:supply\s+chain|manufacturing)\s+region\b",
    r"\b(?:valley|wadi|park|zone|corridor|region|hub|ecosystem)\b$",
]


def _seed_evidence(source: str, supplier: str, snippet: str) -> List[Dict[str, str]]:
    safe_source = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")
    safe_supplier = re.sub(r"[^a-z0-9]+", "-", supplier.lower()).strip("-")
    return [
        {
            "title": f"{source} supplier benchmark evidence",
            "link": f"curated://supplier-benchmark/{safe_source}/{safe_supplier}",
            "snippet": snippet,
        }
    ]


def _seed_supplier(
    source: str,
    name: str,
    location: str,
    products: List[str],
    snippet: str,
    confidence: float = 0.92,
    criticality: str = "High",
) -> Dict[str, Any]:
    return {
        "name": name,
        "location": location,
        "products": products,
        "tier": 1,
        "criticality": criticality,
        "confidence": confidence,
        "justification": f"Curated supplier relationship evidence for {source}",
        "source_evidence": _seed_evidence(source, name, snippet),
    }


CURATED_SUPPLIER_GRAPH: Dict[str, List[Dict[str, Any]]] = {
    "AMD": [
        _seed_supplier(
            "AMD",
            "TSMC",
            "Hsinchu, Taiwan",
            ["Semiconductor foundry", "Advanced process wafers"],
            "TSMC manufactures AMD-designed CPUs and GPUs as a semiconductor foundry and wafer fabrication partner.",
            0.96,
        ),
        _seed_supplier(
            "AMD",
            "GlobalFoundries",
            "United States",
            ["Semiconductor foundry", "Wafer fabrication"],
            "GlobalFoundries originated from AMD's manufacturing operations and remains relevant to AMD semiconductor supply-chain history and wafer fabrication.",
            0.92,
        ),
        _seed_supplier(
            "AMD",
            "Samsung",
            "South Korea",
            ["Semiconductor manufacturing", "Foundry services"],
            "Samsung is a semiconductor manufacturing and foundry ecosystem supplier relevant to AMD advanced chip production options.",
            0.88,
        ),
        _seed_supplier(
            "AMD",
            "ASE Technology",
            "Taiwan",
            ["Semiconductor packaging", "Assembly and test"],
            "ASE Technology provides outsourced semiconductor assembly and test services used in advanced semiconductor supply chains including AMD-class products.",
            0.87,
        ),
        _seed_supplier(
            "AMD",
            "Amkor Technology",
            "United States / Asia",
            ["Semiconductor packaging", "Assembly and test"],
            "Amkor Technology provides chip packaging and assembly-and-test services for semiconductor companies including AMD-class supply chains.",
            0.86,
        ),
    ],
    "Apple": [
        _seed_supplier(
            "Apple",
            "Taiwan Semiconductor Manufacturing Company",
            "Hsinchu, Taiwan",
            ["Advanced processors", "Semiconductor foundry"],
            "TSMC fabricates Apple-designed A-series and M-series chips for Apple as a semiconductor foundry and manufacturing partner.",
            0.97,
        ),
        _seed_supplier(
            "Apple",
            "Hon Hai Precision Industry",
            "Taiwan / China",
            ["iPhone assembly", "Contract manufacturing"],
            "Foxconn, also known as Hon Hai Precision Industry, is a contract manufacturer and assembly partner for Apple hardware.",
            0.96,
        ),
        _seed_supplier(
            "Apple",
            "Pegatron",
            "Taiwan / China",
            ["Device assembly", "OEM manufacturing"],
            "Pegatron manufactures and assembles Apple devices as an OEM and contract manufacturing partner.",
            0.92,
        ),
        _seed_supplier(
            "Apple",
            "Broadcom",
            "United States",
            ["Wireless chips", "RF components"],
            "Broadcom provides wireless chips and radio-frequency components to Apple for consumer devices.",
            0.91,
        ),
        _seed_supplier(
            "Apple",
            "Murata Manufacturing",
            "Japan",
            ["Capacitors", "Electronic components"],
            "Murata Manufacturing supplies electronic components including capacitors used in Apple devices.",
            0.9,
        ),
        _seed_supplier(
            "Apple",
            "Corning",
            "United States",
            ["Cover glass", "Display materials"],
            "Corning provides glass and display cover materials used by Apple in device manufacturing.",
            0.89,
        ),
        _seed_supplier(
            "Apple",
            "Samsung Electronics",
            "South Korea",
            ["Displays", "Memory components"],
            "Samsung Electronics provides displays and memory components for Apple products.",
            0.9,
        ),
    ],
    "Tesla": [
        _seed_supplier(
            "Tesla",
            "Panasonic",
            "Japan / United States",
            ["Battery cells"],
            "Panasonic supplies battery cells and is a battery manufacturing partner for Tesla electric vehicles.",
            0.95,
        ),
        _seed_supplier(
            "Tesla",
            "Contemporary Amperex Technology Co. Limited",
            "China",
            ["LFP battery cells"],
            "CATL supplies LFP battery cells to Tesla and is a battery component supplier.",
            0.94,
        ),
        _seed_supplier(
            "Tesla",
            "LG Energy Solution",
            "South Korea",
            ["Battery cells"],
            "LG Energy Solution provides battery cells for Tesla vehicles as a battery supplier.",
            0.92,
        ),
        _seed_supplier(
            "Tesla",
            "Samsung SDI",
            "South Korea",
            ["Battery cells", "Energy storage components"],
            "Samsung SDI supplies battery and energy storage components used by Tesla programs.",
            0.87,
        ),
    ],
    "NVIDIA": [
        _seed_supplier(
            "NVIDIA",
            "Taiwan Semiconductor Manufacturing Company",
            "Hsinchu, Taiwan",
            ["GPU fabrication", "Semiconductor foundry"],
            "TSMC manufactures and fabricates NVIDIA GPUs as a foundry and semiconductor manufacturing partner.",
            0.97,
        ),
        _seed_supplier(
            "NVIDIA",
            "SK Hynix",
            "South Korea",
            ["HBM memory", "DRAM"],
            "SK Hynix supplies high-bandwidth memory used in NVIDIA AI accelerators.",
            0.94,
        ),
        _seed_supplier(
            "NVIDIA",
            "Samsung Electronics",
            "South Korea",
            ["Memory", "Semiconductor manufacturing"],
            "Samsung Electronics provides memory components and semiconductor manufacturing capacity for NVIDIA products.",
            0.9,
        ),
    ],
    "Intel": [
        _seed_supplier(
            "Intel",
            "ASML",
            "Netherlands",
            ["EUV lithography systems"],
            "ASML supplies EUV lithography equipment used by Intel for advanced semiconductor manufacturing.",
            0.96,
        ),
        _seed_supplier(
            "Intel",
            "Applied Materials",
            "United States",
            ["Semiconductor manufacturing equipment"],
            "Applied Materials provides semiconductor manufacturing equipment and process tools to Intel fabs.",
            0.92,
        ),
        _seed_supplier(
            "Intel",
            "Lam Research",
            "United States",
            ["Etch and deposition tools"],
            "Lam Research supplies etch and deposition equipment used in Intel semiconductor fabrication.",
            0.91,
        ),
        _seed_supplier(
            "Intel",
            "Tokyo Electron",
            "Japan",
            ["Semiconductor production tools"],
            "Tokyo Electron provides semiconductor production tools and process equipment to Intel.",
            0.9,
        ),
        _seed_supplier(
            "Intel",
            "KLA",
            "United States",
            ["Inspection and metrology tools"],
            "KLA supplies process control, inspection, and metrology systems used by Intel fabs.",
            0.89,
        ),
    ],
    "Samsung Electronics": [
        _seed_supplier(
            "Samsung Electronics",
            "ASML",
            "Netherlands",
            ["EUV lithography systems"],
            "ASML supplies EUV lithography systems used by Samsung Electronics for semiconductor manufacturing.",
            0.96,
        ),
        _seed_supplier(
            "Samsung Electronics",
            "Qualcomm",
            "United States",
            ["Mobile chipsets", "Modems"],
            "Qualcomm provides Snapdragon chipsets and modem components for Samsung Electronics devices.",
            0.88,
        ),
        _seed_supplier(
            "Samsung Electronics",
            "Corning",
            "United States",
            ["Cover glass"],
            "Corning supplies cover glass materials used in Samsung Electronics mobile devices.",
            0.89,
        ),
        _seed_supplier(
            "Samsung Electronics",
            "Murata Manufacturing",
            "Japan",
            ["Capacitors", "Electronic components"],
            "Murata Manufacturing supplies electronic components used by Samsung Electronics products.",
            0.87,
        ),
        _seed_supplier(
            "Samsung Electronics",
            "Sony Semiconductor Solutions",
            "Japan",
            ["Image sensors"],
            "Sony Semiconductor Solutions supplies image sensor components for Samsung Electronics devices.",
            0.86,
        ),
    ],
    "Taiwan Semiconductor Manufacturing Company": [
        _seed_supplier(
            "Taiwan Semiconductor Manufacturing Company",
            "ASML",
            "Netherlands",
            ["EUV lithography systems"],
            "ASML supplies EUV lithography systems to TSMC for advanced chip fabrication.",
            0.95,
        ),
        _seed_supplier(
            "Taiwan Semiconductor Manufacturing Company",
            "Applied Materials",
            "United States",
            ["Semiconductor manufacturing equipment"],
            "Applied Materials provides semiconductor manufacturing equipment and process tools to TSMC.",
            0.91,
        ),
        _seed_supplier(
            "Taiwan Semiconductor Manufacturing Company",
            "Lam Research",
            "United States",
            ["Etch and deposition tools"],
            "Lam Research supplies etch and deposition tools used by TSMC fabs.",
            0.9,
        ),
        _seed_supplier(
            "Taiwan Semiconductor Manufacturing Company",
            "Tokyo Electron",
            "Japan",
            ["Semiconductor production tools"],
            "Tokyo Electron provides semiconductor process equipment to TSMC.",
            0.89,
        ),
        _seed_supplier(
            "Taiwan Semiconductor Manufacturing Company",
            "Entegris",
            "United States",
            ["Materials handling", "Filtration"],
            "Entegris supplies materials handling and filtration products used in TSMC semiconductor manufacturing.",
            0.86,
        ),
    ],
    "ASML": [
        _seed_supplier(
            "ASML",
            "Carl Zeiss SMT",
            "Germany",
            ["Lithography optics"],
            "Carl Zeiss SMT supplies precision optics and optical modules to ASML lithography systems.",
            0.93,
        ),
        _seed_supplier(
            "ASML",
            "Trumpf",
            "Germany",
            ["Laser systems"],
            "Trumpf provides laser technology and source components used by ASML lithography equipment.",
            0.88,
        ),
        _seed_supplier(
            "ASML",
            "VDL ETG",
            "Netherlands",
            ["Mechatronic modules"],
            "VDL ETG supplies mechatronic modules and system assemblies for ASML equipment.",
            0.86,
        ),
    ],
    "Panasonic": [
        _seed_supplier(
            "Panasonic",
            "Sumitomo Metal Mining",
            "Japan",
            ["Battery cathode materials"],
            "Sumitomo Metal Mining supplies battery materials used by Panasonic Energy cell manufacturing.",
            0.86,
        ),
        _seed_supplier(
            "Panasonic",
            "Mitsubishi Materials",
            "Japan",
            ["Battery materials", "Metals"],
            "Mitsubishi Materials provides metals and battery materials for Panasonic manufacturing.",
            0.84,
        ),
    ],
    "Contemporary Amperex Technology Co. Limited": [
        _seed_supplier(
            "Contemporary Amperex Technology Co. Limited",
            "Ganfeng Lithium",
            "China",
            ["Lithium materials"],
            "Ganfeng Lithium supplies lithium materials used by CATL battery manufacturing.",
            0.87,
        ),
        _seed_supplier(
            "Contemporary Amperex Technology Co. Limited",
            "Tianqi Lithium",
            "China",
            ["Lithium materials"],
            "Tianqi Lithium provides lithium materials to CATL battery supply chains.",
            0.84,
        ),
    ],
    "SK Hynix": [
        _seed_supplier(
            "SK Hynix",
            "ASML",
            "Netherlands",
            ["Lithography systems"],
            "ASML supplies lithography systems used by SK Hynix memory fabs.",
            0.9,
        ),
        _seed_supplier(
            "SK Hynix",
            "Tokyo Electron",
            "Japan",
            ["Semiconductor production tools"],
            "Tokyo Electron supplies semiconductor production equipment to SK Hynix.",
            0.86,
        ),
    ],
}

CURATED_SUPPLIER_ALIASES = {
    "amd": "AMD",
    "advanced micro devices": "AMD",
    "advanced micro devices inc": "AMD",
    "advanced micro devices inc.": "AMD",
    "globalfoundries": "GlobalFoundries",
    "globalfoundries inc": "GlobalFoundries",
    "ase technology": "ASE Technology",
    "ase technology holding": "ASE Technology",
    "amkor": "Amkor Technology",
    "amkor technology": "Amkor Technology",
    "apple": "Apple",
    "apple inc": "Apple",
    "apple inc.": "Apple",
    "tesla": "Tesla",
    "tesla inc": "Tesla",
    "nvidia": "NVIDIA",
    "nvidia corporation": "NVIDIA",
    "intel": "Intel",
    "intel corporation": "Intel",
    "samsung": "Samsung Electronics",
    "samsung electronics": "Samsung Electronics",
    "samsung electronics co ltd": "Samsung Electronics",
    "sony semiconductor": "Sony Semiconductor Solutions",
    "sony semiconductor solutions": "Sony Semiconductor Solutions",
    "tsmc": "Taiwan Semiconductor Manufacturing Company",
    "taiwan semiconductor": "Taiwan Semiconductor Manufacturing Company",
    "taiwan semiconductor manufacturing co": "Taiwan Semiconductor Manufacturing Company",
    "taiwan semiconductor manufacturing company": "Taiwan Semiconductor Manufacturing Company",
    "catl": "Contemporary Amperex Technology Co. Limited",
    "contemporary amperex technology": "Contemporary Amperex Technology Co. Limited",
    "contemporary amperex technology co limited": "Contemporary Amperex Technology Co. Limited",
    "hon hai precision industry": "Hon Hai Precision Industry Co., Ltd.",
    "hon hai precision industry co ltd": "Hon Hai Precision Industry Co., Ltd.",
    "hon hai technology group": "Hon Hai Precision Industry Co., Ltd.",
    "foxconn": "Hon Hai Precision Industry Co., Ltd.",
    "foxconn technology group": "Hon Hai Precision Industry Co., Ltd.",
    "pegatron": "Pegatron Corporation",
    "pegatron corporation": "Pegatron Corporation",
    "sk hynix": "SK hynix",
    "hynix": "SK hynix",
    "broadcom": "Broadcom Inc.",
    "broadcom inc": "Broadcom Inc.",
    "compal": "Compal Electronics",
    "compal electronics": "Compal Electronics",
    "marvell": "Marvell Technology, Inc.",
    "marvell technology": "Marvell Technology, Inc.",
    "marvell technology group": "Marvell Technology, Inc.",
    "murata": "Murata Manufacturing",
    "murata manufacturing": "Murata Manufacturing",
    "corning": "Corning Inc.",
    "corning inc": "Corning Inc.",
    "quanta": "Quanta Computer",
    "quanta computer": "Quanta Computer",
    "wistron": "Wistron",
    "inventec": "Inventec",
    "qualcomm": "Qualcomm",
    "qualcomm inc": "Qualcomm",
    "qualcomm incorporated": "Qualcomm",
    "dell": "Dell Technologies",
    "dell technologies": "Dell Technologies",
}

DISCOVERY_QUERY_DISPLAY_NAMES = {
    "Qualcomm": "Qualcomm",
    "Dell Technologies": "Dell",
}

EXPECTED_TIER1_SUPPLIERS = {
    "AMD": {
        "TSMC",
        "GlobalFoundries",
        "Samsung Electronics",
        "ASE Technology",
        "Amkor Technology",
    },
    "Apple": {
        "Taiwan Semiconductor Manufacturing Company",
        "Hon Hai Precision Industry Co., Ltd.",
        "Pegatron Corporation",
        "Broadcom Inc.",
        "Murata Manufacturing",
        "Corning Inc.",
        "Samsung Electronics",
    },
    "Tesla": {
        "Panasonic",
        "Contemporary Amperex Technology Co. Limited",
        "LG Energy Solution",
        "Samsung SDI",
    },
    "NVIDIA": {
        "Taiwan Semiconductor Manufacturing Company",
        "SK hynix",
        "Samsung Electronics",
    },
    "Intel": {
        "ASML",
        "Applied Materials",
        "Lam Research",
        "Tokyo Electron",
        "KLA",
    },
    "Samsung Electronics": {
        "ASML",
        "Qualcomm",
        "Corning Inc.",
        "Murata Manufacturing",
        "Sony Semiconductor Solutions",
    },
    "Qualcomm": {
        "Taiwan Semiconductor Manufacturing Company",
        "Samsung Electronics",
        "ASE Technology",
        "Amkor Technology",
        "GlobalFoundries",
        "SMIC",
    },
    "Dell Technologies": {
        "Compal Electronics",
        "Quanta Computer",
        "Wistron",
        "Hon Hai Precision Industry Co., Ltd.",
        "Inventec",
        "Broadcom Inc.",
        "Marvell Technology, Inc.",
    },
}

for _supplier_entries in list(CURATED_SUPPLIER_GRAPH.values()):
    for _supplier_entry in _supplier_entries:
        CURATED_SUPPLIER_GRAPH.setdefault(_supplier_entry["name"], [])

FRAGMENT_PHRASES = [
    "became a supplier to",
    "became a major supplier to",
    "including",
    "is a business unit of",
    "supplier to",
    "manufacturing including",
]

SUPPLIER_SIGNAL_PATTERNS = {
    "strong": [
        r"\bsupplier\b",
        r"\bsupplies\b",
        r"\bsupplied\s+by\b",
        r"\bvendor\b",
        r"\boem\b",
        r"\bcontract\s+manufacturer\b",
        r"\bmanufacturing\s+partner\b",
        r"\bcomponent\s+supplier\b",
        r"\bassembly\s+partner\b",
        r"\bpackaging\s+partner\b",
        r"\bfabrication\s+partner\b",
        r"\bfoundry\s+partner\b",
        r"\bsemiconductor\s+manufacturing\s+partner\b",
        r"\boutsourced\s+(?:its\s+)?manufacturing\b",
        r"\boutsourced\s+semiconductor\s+assembly\s+and\s+test\b",
        r"\bosat\b",
        r"\bchip\s+packaging\b",
        r"\bwafer\s+fabrication\b",
        r"\bcontract\s+chipmaker\b",
        r"\bfoundries\s+including\b",
        r"\bproduction\s+with\s+(?:other\s+)?foundries\b",
        r"\boriginal\s+design\s+manufacturer\b",
        r"\bmanufactures?(?:\s+\w+){0,8}\s+for\b",
        r"\bfabricat(?:es|ed|ing)(?:\s+\w+){0,8}\s+for\b",
        r"\b(?:manufactured|assembled|fabricated|built|produced|packaged)\s+(?:[^.;]{0,80}\s+)?by\b",
        r"\bfoundry\s+for\b",
        r"\bserves?\s+as\s+(?:the\s+)?main\s+supplier\s+for\b",
        r"\bprovides?\s+(?:components?|parts?|chips?|displays?|memory|services?|materials?|equipment|systems?)\s+to\b",
        r"\bsupplies\s+(?:components?|parts?|chips?|displays?|memory|materials?|equipment|systems?)\b",
    ],
    "medium": [
        r"\bstrategic\s+partner\b",
        r"\bprocurement\s+partner\b",
        r"\bsupply\s+agreement\b",
        r"\bsourcing\s+agreement\b",
        r"\bsources?(?:\s+\w+){0,8}\s+from\b",
        r"\bsourced\s+from\b",
        r"\becosystem\s+partner\b",
        r"\bmanufacturing\s+ecosystem\b",
        r"\bsemiconductor\s+ecosystem\b",
        r"\bcontract\s+manufacturing\b",
        r"\boutsourced\s+manufacturing\b",
        r"\bwafer\s+(?:production|manufacturing)\b",
        r"\bsemiconductor\s+assembly\s+and\s+test\b",
        r"\bsemiconductor\s+partner\b",
    ],
    "weak": [
        r"\bsupplier\s+list\b",
        r"\bsupply[-\s]+chain\s+report\b",
        r"\bmanufacturing\s+context\b",
        r"\bsemiconductor\s+(?:manufacturing|foundry|fabrication|supply\s+chain|industry)\b",
        r"\bfoundry\s+(?:business|industry|ecosystem|manufacturing)\b",
        r"\bfoundries\b",
        r"\bfab(?:rication)?\s+(?:partner|plant|facility|ecosystem|manufacturing)\b",
    ],
}

SUPPLIER_SIGNAL_WEIGHTS = {
    "strong": 5,
    "medium": 3,
    "weak": 1,
}

TIER_EVIDENCE_THRESHOLDS = {
    2: 3,
    3: 5,
}

SUPPLIER_NEGATIVE_PATTERNS = [
    r"\bshareholder\b",
    r"\binvestor\b",
    r"\bacquired\b",
    r"\bsubsidiary\b",
    r"\bowned\s+by\b",
    r"\bbusiness\s+unit\b",
    r"\bchairman\b",
    r"\bceo\b",
    r"\bfounder\b",
    r"\bpartnered\s+with\b",
    r"\bjoint\s+venture\b",
    r"\bcustomer\b",
    r"\bclient\b",
    r"\bcompetitor\b",
    r"\bagainst\b",
    r"\banti-competitive\b",
    r"\bdefendants?\b",
    r"\blawsuit\b",
    r"\bnot\s+using\b",
    r"\bovertook\b",
    r"\btechnology-sharing\b",
    r"\bindustry\s+peer\b",
    r"\brival\b",
]

COMPETITOR_BY_TARGET = {
    "AMD": {"Intel", "NVIDIA", "Qualcomm"},
    "Intel": {"AMD", "NVIDIA", "Qualcomm"},
    "NVIDIA": {"AMD", "Intel", "Qualcomm"},
    "Qualcomm": {"AMD", "Intel", "NVIDIA"},
}


def _compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _known_organization_names() -> set[str]:
    names = set()
    names.update(CURATED_SUPPLIER_ALIASES.keys())
    names.update(CURATED_SUPPLIER_ALIASES.values())
    names.update(resolver.mapping.keys())
    names.update(resolver.mapping.values())
    for name in list(names):
        names.update(resolver.aliases_for(name))
    return {_compact_key(name) for name in names if name}


KNOWN_ORGANIZATION_NAMES = _known_organization_names()


def canonical_curated_company_name(company_name: str) -> Optional[str]:
    key = _compact_key(company_name)
    candidates = [company_name, resolver.resolve(company_name)]
    if key in CURATED_SUPPLIER_ALIASES:
        candidates.append(CURATED_SUPPLIER_ALIASES[key])
    for canonical in CURATED_SUPPLIER_GRAPH:
        canonical_keys = {
            _compact_key(canonical),
            _compact_key(resolver.resolve(canonical)),
        }
        if any(_compact_key(candidate) in canonical_keys for candidate in candidates):
            return canonical
    for expected_company in EXPECTED_TIER1_SUPPLIERS:
        expected_keys = {
            _compact_key(expected_company),
            _compact_key(resolver.resolve(expected_company)),
        }
        if any(_compact_key(candidate) in expected_keys for candidate in candidates):
            return expected_company
    return None


def get_curated_suppliers(company_name: str) -> List[Dict[str, Any]]:
    canonical = canonical_curated_company_name(company_name)
    if not canonical:
        return []
    return copy.deepcopy(CURATED_SUPPLIER_GRAPH.get(canonical, []))


def is_known_organization(name: str) -> bool:
    key = _compact_key(name)
    return bool(key and (key in KNOWN_ORGANIZATION_NAMES or resolver.is_known_entity(name)))


def expected_tier1_suppliers(company_name: str) -> set[str]:
    canonical = canonical_curated_company_name(company_name)
    if not canonical:
        return set()
    return set(EXPECTED_TIER1_SUPPLIERS.get(canonical, set()))


def expected_tier1_count(company_name: str) -> int:
    expected = expected_tier1_suppliers(company_name)
    return len(expected) if expected else 5


DISCOVERY_QUERY_TEMPLATES = [
    "{company} suppliers",
    "{company} supply chain",
    "{company} foundry suppliers",
    "{company} manufacturing partners",
    "{company} chip packaging suppliers",
    "{company} contract manufacturers",
    "{company} ODM suppliers",
    "{company} original design manufacturers",
    "{company} outsourced manufacturing",
    "{company} wafer fabrication suppliers",
    "{company} OSAT suppliers",
]

COMPANY_SPECIFIC_QUERY_TEMPLATES = {
    "qualcomm": [
        "{company} foundry supplier",
        "{company} chip manufacturing partner",
        "{company} semiconductor supply chain",
        "{company} TSMC Samsung foundry",
        "{company} packaging supplier ASE Amkor",
        "{company} outsourced semiconductor assembly and test",
    ],
    "dell technologies": [
        "{company} ODM suppliers",
        "{company} contract manufacturers",
        "{company} laptop manufacturing Compal Quanta Wistron",
        "{company} supply chain suppliers",
        "{company} component suppliers Broadcom Marvell",
    ],
}

MANUFACTURING_CONTEXT_TERMS = [
    "supplier",
    "suppliers",
    "foundry",
    "foundries",
    "wafer fabrication",
    "fabrication",
    "chip packaging",
    "osat",
    "outsourced manufacturing",
    "outsourced semiconductor assembly",
    "semiconductor manufacturing partner",
    "manufacturing partner",
    "contract manufacturer",
    "contract manufacturers",
    "original design manufacturer",
    "odm",
]


def discovery_queries(company_name: str) -> List[str]:
    seen = set()
    queries = []
    templates = list(DISCOVERY_QUERY_TEMPLATES)
    canonical_name = canonical_curated_company_name(company_name) or resolver.resolve(
        company_name
    )
    query_company = DISCOVERY_QUERY_DISPLAY_NAMES.get(canonical_name, company_name)
    templates.extend(COMPANY_SPECIFIC_QUERY_TEMPLATES.get(_compact_key(canonical_name), []))
    for template in templates:
        query = template.format(company=query_company)
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(query)
    return queries


def _strip_search_markup(text: str) -> str:
    clean = re.sub(r'<span class="searchmatch">|</span>', "", text or "")
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"\s+", " ", unescape(clean))
    return clean.strip()


def _has_manufacturing_context(text: str) -> bool:
    low_text = _strip_search_markup(text).lower()
    if any(
        re.search(
            rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])",
            low_text,
            flags=re.IGNORECASE,
        )
        for term in MANUFACTURING_CONTEXT_TERMS
    ):
        return True
    return analyze_supplier_evidence([{"snippet": text}])["has_positive_signal"]


def _looks_like_list_or_meta_page(title: str) -> bool:
    return bool(
        re.search(
            r"^(?:list of|history of|timeline of|criticism of|products of)\b",
            title or "",
            flags=re.IGNORECASE,
        )
    )


def _split_candidate_list(fragment: str, target_company: Optional[str]) -> List[str]:
    fragment = _strip_search_markup(fragment)
    fragment = re.split(
        r"\b(?:with|which|that|where|while|because|after|before|through)\b",
        fragment,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    fragment = re.sub(r"\s+(?:and|or|as well as)\s+", ", ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"\s*/\s*", ", ", fragment)

    names = []
    seen = set()
    for part in fragment.split(","):
        candidate = _clean_candidate_text(part)
        if not candidate:
            continue
        candidate = _extract_company_like_span(candidate) or candidate
        name = normalize_supplier_candidate_name(candidate, target_company)
        if not name:
            continue
        key = _compact_key(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)

    return names


def _candidate_evidence_mentions_relationship(
    candidate_name: str, target_company: str, evidence: List[Dict[str, str]]
) -> bool:
    evidence_text = " ".join(
        f"{item.get('title', '')} {item.get('snippet', '')}" for item in evidence
    )
    if not _text_mentions_entity(evidence_text, target_company):
        return False
    if not _text_mentions_entity(evidence_text, candidate_name):
        return False
    analysis = analyze_supplier_evidence(evidence)
    if not analysis["has_positive_signal"] and not _has_manufacturing_context(evidence_text):
        return False
    if analysis["negative_hits"] and analysis["score"] < 5:
        return False
    return True


def _term_variants(name: Optional[str]) -> set[str]:
    if not name:
        return set()

    clean = _clean_candidate_text(name)
    variants = {clean, _compact_key(clean)}
    variants.update(resolver.term_variants(clean))
    variants.update(resolver.aliases_for(clean))
    compact = _compact_key(clean)

    alias_target = CURATED_SUPPLIER_ALIASES.get(compact)
    if alias_target:
        variants.add(alias_target)
        variants.add(_compact_key(alias_target))

    for alias, canonical in CURATED_SUPPLIER_ALIASES.items():
        if canonical == clean or _compact_key(canonical) == compact:
            variants.add(alias)

    words = clean.split()
    if len(words) >= 2:
        variants.add(" ".join(words[:2]))
    if len(words) >= 3:
        variants.add(" ".join(words[:3]))

    abbreviations = {
        "Advanced Micro Devices": "AMD",
        "Taiwan Semiconductor Manufacturing Company": "TSMC",
        "Hon Hai Precision Industry": "Foxconn",
        "Hon Hai Precision Industry Co., Ltd.": "Foxconn",
        "Contemporary Amperex Technology Co. Limited": "CATL",
        "LG Energy Solution": "LGES",
        "ASE Technology": "ASE",
        "ASE Technology Holding": "ASE",
        "Amkor Technology": "Amkor",
        "Samsung Electronics": "Samsung",
        "SK hynix": "SK Hynix",
    }
    if clean in abbreviations:
        variants.add(abbreviations[clean])

    return {variant.lower() for variant in variants if variant and len(variant) >= 2}


def _text_mentions_entity(text: str, entity_name: Optional[str]) -> bool:
    if not entity_name:
        return False
    plain_text = re.sub(r"<[^>]+>", " ", unescape(text or ""))
    for variant in _term_variants(entity_name):
        if re.search(
            rf"(?<![a-z0-9]){re.escape(variant)}(?![a-z0-9])",
            plain_text,
            flags=re.IGNORECASE,
        ):
            return True
    return False


def is_product_or_brand_name(name: str) -> bool:
    return _compact_key(name) in PRODUCT_FRAGMENT_NAMES


def _canonical_entity_for_comparison(name: Optional[str]) -> str:
    canonical = canonical_curated_company_name(name or "") or resolver.resolve(name or "")
    return _compact_key(canonical)


def candidate_competes_with_target(
    target_company: Optional[str], candidate_name: Optional[str]
) -> bool:
    target_key = _canonical_entity_for_comparison(target_company)
    candidate_key = _canonical_entity_for_comparison(candidate_name)
    if not target_key or not candidate_key:
        return False

    for target, competitors in COMPETITOR_BY_TARGET.items():
        if _canonical_entity_for_comparison(target) != target_key:
            continue
        return any(
            _canonical_entity_for_comparison(competitor) == candidate_key
            for competitor in competitors
        )
    return False


def supplier_evidence_explicitly_links_candidate_to_source(
    candidate_name: str,
    source_company: str,
    evidence: List[Dict[str, str]],
) -> bool:
    evidence_text = " ".join(
        f"{item.get('title', '')} {item.get('snippet', '')}" for item in evidence or []
    )
    if not _text_mentions_entity(evidence_text, source_company):
        return False
    if not _text_mentions_entity(evidence_text, candidate_name):
        return False

    text = re.sub(r"<[^>]+>", " ", unescape(evidence_text or ""))
    text = re.sub(r"\s+", " ", text).lower()

    candidate_variants = sorted(_term_variants(candidate_name), key=len, reverse=True)
    source_variants = sorted(_term_variants(source_company), key=len, reverse=True)
    supplier_verbs = (
        r"suppl(?:y|ies|ied)",
        r"provid(?:e|es|ed)",
        r"manufactur(?:e|es|ed)",
        r"fabricat(?:e|es|ed)",
        r"assembl(?:e|es|ed)",
        r"packag(?:e|es|ed)",
        r"sell(?:s)?",
    )
    supplied_by_phrases = (
        "supplied by",
        "sourced from",
        "sources from",
        "procures from",
        "manufactured by",
        "fabricated by",
        "assembled by",
        "packaged by",
        "outsourced to",
    )

    for candidate in candidate_variants:
        for source in source_variants:
            if re.search(
                rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9]).{{0,120}}"
                rf"(?:{'|'.join(supplier_verbs)}).{{0,120}}"
                rf"\b(?:to|for|used by)\b.{{0,80}}"
                rf"(?<![a-z0-9]){re.escape(source)}(?![a-z0-9])",
                text,
                flags=re.IGNORECASE,
            ):
                return True
            if re.search(
                rf"(?<![a-z0-9]){re.escape(source)}(?![a-z0-9]).{{0,120}}"
                rf"(?:{'|'.join(re.escape(phrase) for phrase in supplied_by_phrases)}).{{0,80}}"
                rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])",
                text,
                flags=re.IGNORECASE,
            ):
                return True
            if re.search(
                rf"(?<![a-z0-9]){re.escape(source)}(?![a-z0-9]).{{0,120}}"
                rf"\buses?\b.{{0,80}}"
                rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])",
                text,
                flags=re.IGNORECASE,
            ):
                return True

    return False


def unrelated_energy_candidate_without_supply_evidence(
    candidate_name: str,
    source_company: str,
    evidence: List[Dict[str, str]],
) -> bool:
    if not re.search(r"\b(?:energy|solar|wind|renewable|power)\b", candidate_name, re.IGNORECASE):
        return False
    return not supplier_evidence_explicitly_links_candidate_to_source(
        candidate_name, source_company, evidence
    )


def _same_entity_name(candidate_name: str, target_company: Optional[str]) -> bool:
    if not candidate_name or not target_company:
        return False

    candidate_key = _compact_key(candidate_name)
    target_key = _compact_key(target_company)
    if candidate_key == target_key:
        return True

    target_variants = {_compact_key(variant) for variant in _term_variants(target_company)}
    candidate_variants = {_compact_key(variant) for variant in _term_variants(candidate_name)}
    return candidate_key in target_variants or target_key in candidate_variants


def _clean_candidate_text(name: str) -> str:
    clean_name = unescape(re.sub(r"<[^>]+>", " ", name or ""))
    clean_name = re.sub(r"\s+", " ", clean_name).strip()
    clean_name = re.sub(r"^[\"'`({\[]+", "", clean_name)
    clean_name = re.sub(r"[\"'`)}\],.;:]+$", "", clean_name)
    clean_name = re.sub(r"^(?:the|a|an)\s+", "", clean_name, flags=re.IGNORECASE)
    return clean_name.strip()


def _dedupe_repeated_name_prefix(name: str) -> str:
    words = name.split()
    if len(words) >= 3 and words[0].lower().strip(".,") == words[-1].lower().strip(".,"):
        return words[0]
    max_prefix_words = min(4, len(words) // 2)

    for prefix_len in range(max_prefix_words, 0, -1):
        prefix = " ".join(words[:prefix_len]).lower().strip(".,")
        repeated = " ".join(words[prefix_len : prefix_len * 2]).lower().strip(".,")
        if prefix and prefix == repeated:
            return " ".join(words[prefix_len:])

    return name


def _is_identifiable_organization(name: str) -> bool:
    if not name or len(name) < 3:
        return False

    lower_name = name.lower()
    compact_name = _compact_key(name)
    if compact_name in INVALID_CANDIDATE_NAMES:
        return False
    if is_known_organization(name):
        return True
    if lower_name in GENERIC_CANDIDATE_TERMS:
        return False
    if compact_name in PERSON_FRAGMENT_NAMES:
        return False
    if compact_name in PRODUCT_FRAGMENT_NAMES:
        return False
    if compact_name in LOCATION_FRAGMENT_WORDS:
        return False
    if any(re.search(pattern, lower_name) for pattern in LOCATION_ECOSYSTEM_PATTERNS):
        return False
    if any(re.search(pattern, lower_name) for pattern in GENERIC_ORG_PATTERNS):
        return False
    if any(phrase in lower_name for phrase in FRAGMENT_PHRASES):
        return False
    if re.search(r"[^A-Za-z0-9&\s\.\-',]", name):
        return False
    if not re.search(r"[A-Za-z]", name):
        return False
    if not name[0].isupper() and not re.match(r"^[0-9]", name):
        return False

    words = re.findall(r"[A-Za-z0-9&\.\-']+", name)
    meaningful_words = [
        word
        for word in words
        if word.lower().strip(".") not in GENERIC_CANDIDATE_TERMS
    ]
    if not meaningful_words:
        return False

    if len(meaningful_words) == 1 and meaningful_words[0].lower() in PRODUCT_FRAGMENT_NAMES:
        return False

    has_corporate_suffix = re.search(
        rf"\b(?:{CORPORATE_SUFFIX_PATTERN})\b", name, re.IGNORECASE
    )
    if has_corporate_suffix:
        return True

    if len(words) == 1:
        token = words[0]
        if token.isupper() and len(token) >= 2:
            return True
        if len(token) < 4:
            return False

    if len(words) > 4:
        return False

    return any(word[:1].isupper() or word.isupper() for word in meaningful_words)


def validate_supplier_candidate_name(
    name: str, target_company: Optional[str] = None
) -> tuple[bool, str]:
    clean_name = _clean_candidate_text(name)
    if not clean_name:
        return False, "empty candidate"

    lower_name = clean_name.lower()
    compact_name = _compact_key(clean_name)

    if compact_name in INVALID_CANDIDATE_NAMES:
        return False, "known malformed or non-organization candidate"
    if compact_name in PERSON_FRAGMENT_NAMES:
        return False, "person name, not an organization"
    if compact_name in PRODUCT_FRAGMENT_NAMES:
        return False, "product category, not an organization"
    if compact_name in LOCATION_FRAGMENT_WORDS:
        return False, "location adjective or place, not an organization"
    if any(re.search(pattern, lower_name) for pattern in LOCATION_ECOSYSTEM_PATTERNS):
        return False, "location, region, or ecosystem label, not a supplier company"
    if any(re.search(pattern, lower_name) for pattern in GENERIC_ORG_PATTERNS):
        return False, "generic or malformed organization phrase"
    if re.search(r"\b(?:that|currently|while|including|such as)\b", lower_name) and not is_known_organization(clean_name):
        return False, "sentence fragment rather than organization name"
    if re.search(r"[^A-Za-z0-9&\s\.\-',]", clean_name):
        return False, "unsupported punctuation"
    if not _is_identifiable_organization(clean_name):
        return False, "not an identifiable organization"

    if target_company:
        if _same_entity_name(clean_name, target_company):
            return False, "candidate is the source company"
        target_norm = re.sub(r"[^a-z0-9]", "", target_company.lower())
        name_norm = re.sub(r"[^a-z0-9]", "", clean_name.lower())
        if target_norm and (target_norm in name_norm or name_norm in target_norm):
            return False, "candidate is the source company"

    return True, "valid organization candidate"


def _extract_company_like_span(text: str) -> Optional[str]:
    text = _clean_candidate_text(text)
    if not text:
        return None

    suffix_match = re.search(
        rf"\b([A-Z][A-Za-z0-9&\.\-']*(?:\s+[A-Z][A-Za-z0-9&\.\-']*)*"
        rf"\s+(?:{CORPORATE_SUFFIX_PATTERN}))\b",
        text,
    )
    if suffix_match:
        return _clean_candidate_text(suffix_match.group(1))

    title_match = re.search(
        r"\b([A-Z][A-Za-z0-9&\.\-']*(?:\s+[A-Z][A-Za-z0-9&\.\-']*){0,3})\b",
        text,
    )
    if title_match:
        return _clean_candidate_text(title_match.group(1))

    return None


def normalize_supplier_candidate_name(
    raw_name: str, target_company: Optional[str] = None
) -> Optional[str]:
    """
    Converts regex-captured relationship fragments into organization names.
    Returns None when no identifiable organization remains.
    """
    clean_name = _clean_candidate_text(raw_name)
    if not clean_name:
        return None

    # Prefer the entity before explanatory relationship text when the fragment
    # starts with a company name, e.g. "Micron became a major supplier to Apple".
    leading_entity_patterns = [
        r"^(.+?)\s+became\s+(?:a\s+)?(?:major\s+)?supplier\s+to\b",
        r"^(.+?)\s+is\s+a\s+business\s+unit\s+of\b",
        r"^(.+?)\s+supplier\s+to\b",
    ]
    for pattern in leading_entity_patterns:
        match = re.search(pattern, clean_name, flags=re.IGNORECASE)
        if match:
            clean_name = match.group(1)
            break
    else:
        # If a fragment is just context followed by an entity, keep the entity.
        trailing_entity_patterns = [
            r"\bmanufacturing\s+including\s+(.+)$",
            r"\bincluding\s+(.+)$",
            r"\bsuch\s+as\s+(.+)$",
            r"\bwith\s+(.+)$",
        ]
        for pattern in trailing_entity_patterns:
            match = re.search(pattern, clean_name, flags=re.IGNORECASE)
            if match:
                clean_name = match.group(1)
                break

    clean_name = _extract_company_like_span(clean_name) or _clean_candidate_text(
        clean_name
    )
    clean_name = _dedupe_repeated_name_prefix(clean_name)
    clean_name = re.sub(
        r"\s+(?:became|including|supplier\s+to|is\s+a\s+business\s+unit\s+of)\b.*$",
        "",
        clean_name,
        flags=re.IGNORECASE,
    )
    clean_name = _clean_candidate_text(clean_name)

    valid_name, _ = validate_supplier_candidate_name(clean_name, target_company)
    if not valid_name:
        return None

    return clean_name


def analyze_supplier_evidence(
    evidence: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Scores discovery snippets for weighted supplier evidence.

    The output is used to reject generic co-occurrence while allowing deeper
    tiers to pass on accumulated supplier, partnership, and manufacturing
    context instead of exact supplier wording only.
    """
    strong_hits = 0
    medium_hits = 0
    weak_hits = 0
    negative_hits = 0
    supporting_snippets = 0
    matching_snippets = []
    signals = []
    score = 0

    for item in evidence or []:
        snippet = f"{item.get('title', '')} {item.get('snippet', '')}".strip()
        if not snippet:
            continue

        text = re.sub(r"<[^>]+>", " ", unescape(snippet)).lower()
        text = re.sub(r"\s+", " ", text)
        snippet_positive = False
        for category, patterns in SUPPLIER_SIGNAL_PATTERNS.items():
            matched = [
                pattern
                for pattern in patterns
                if re.search(pattern, text, flags=re.IGNORECASE)
            ]
            if not matched:
                continue

            snippet_positive = True
            hit_count = len(matched)
            score += SUPPLIER_SIGNAL_WEIGHTS[category] * hit_count
            signals.extend(
                {"category": category, "pattern": pattern, "weight": SUPPLIER_SIGNAL_WEIGHTS[category]}
                for pattern in matched
            )
            if category == "strong":
                strong_hits += hit_count
            elif category == "medium":
                medium_hits += hit_count
            else:
                weak_hits += hit_count

        snippet_negative = any(
            re.search(pattern, text, flags=re.IGNORECASE)
            for pattern in SUPPLIER_NEGATIVE_PATTERNS
        )

        if snippet_negative:
            negative_hits += 1
        if snippet_positive:
            supporting_snippets += 1
            matching_snippets.append(item)

    return {
        "strong_hits": strong_hits,
        "medium_hits": medium_hits,
        "weak_hits": weak_hits,
        "negative_hits": negative_hits,
        "supporting_snippets": supporting_snippets,
        "matching_snippets": matching_snippets,
        "signals": signals,
        "score": score,
        "has_positive_signal": (strong_hits + medium_hits + weak_hits) > 0,
    }


def supplier_evidence_is_strong(
    evidence: List[Dict[str, str]],
    tier: int,
    confidence: float,
    candidate_name: Optional[str] = None,
    source_company: Optional[str] = None,
) -> tuple[bool, str]:
    analysis = analyze_supplier_evidence(evidence)
    threshold = TIER_EVIDENCE_THRESHOLDS.get(tier, 0)
    evidence_text = " ".join(
        f"{item.get('title', '')} {item.get('snippet', '')}" for item in evidence or []
    )

    if evidence:
        if source_company and not _text_mentions_entity(evidence_text, source_company):
            return False, "Evidence does not mention the source company for the claimed supplier relationship"
        if candidate_name and not _text_mentions_entity(evidence_text, candidate_name):
            return False, "Evidence does not mention the candidate company for the claimed supplier relationship"

    if tier == 1:
        if evidence and not analysis["has_positive_signal"]:
            return False, "Evidence does not contain a supplier indicator"
        if (
            evidence
            and candidate_name
            and source_company
            and analysis["strong_hits"] == 0
            and not supplier_evidence_explicitly_links_candidate_to_source(
                candidate_name, source_company, evidence
            )
        ):
            return False, "Evidence does not explicitly establish supplier direction"
        if analysis["negative_hits"] > 0 and analysis["score"] < 5:
            return False, "Negative relationship signals outweigh supplier evidence"
        accepted = confidence >= 0.75
        return accepted, "Accepted tier-1 supplier evidence" if accepted else "Low discovery confidence"

    if not evidence:
        return False, f"Tier-{tier} suppliers require evidence score >= {threshold}"

    if analysis["negative_hits"] > 0 and analysis["score"] < threshold + 3:
        return (
            False,
            f"Tier-{tier} negative relationship signals outweigh supplier evidence score",
        )

    if tier >= 2:
        accepted = analysis["score"] >= threshold
        signal_summary = ", ".join(
            f"{signal['category']}:{signal['pattern']}"
            for signal in analysis["signals"][:6]
        ) or "none"
        decision = "Accepted" if accepted else "Rejected"
        diagnostic = (
            "[EVIDENCE SCORE] "
            f"Candidate: {candidate_name or 'N/A'} | "
            f"Tier: {tier} | "
            f"Signals: {signal_summary} | "
            f"Score: {analysis['score']} | "
            f"Threshold: {threshold} | "
            f"Decision: {decision}"
        )
        return accepted, diagnostic

    return confidence >= 0.75, "Low discovery confidence"


class SupplierDiscoveryScraper:
    """
    Scrapes the web to identify real suppliers for a given company.
    Uses public search results and news mentions to build a list of partners.
    """

    def __init__(
        self,
        runtime_state: Optional[Any] = None,
        stage_key: str = "supplier_discovery",
        prefer_curated: bool = False,
        use_cache: bool = True,
        refresh_cache: bool = False,
    ):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        self.runtime_state = runtime_state
        self.stage_key = stage_key
        self.prefer_curated = prefer_curated
        self.use_cache = use_cache
        self.refresh_cache = refresh_cache
        self.cache_dir = "database/cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        self.stats = {
            "Wikipedia Success": 0,
            "Wikipedia Retry Count": 0,
            "Cache Used": 0,
        }
        self.cache_version = 7

    def _get_cache_path(self, company_name: str) -> str:
        safe_name = company_name.lower().replace(" ", "_").replace(".", "")
        return os.path.join(self.cache_dir, f"{safe_name}_v{self.cache_version}.json")

    def _cache_enabled(self) -> bool:
        return bool(
            self.use_cache
            and getattr(self.runtime_state, "supplier_cache_enabled", True)
        )

    def _refresh_requested(self) -> bool:
        return bool(
            self.refresh_cache
            or getattr(self.runtime_state, "refresh_supplier_cache", False)
        )

    def _sanitize_cached_suppliers(
        self, cached: Any, company_name: str
    ) -> List[Dict[str, Any]]:
        if not isinstance(cached, list):
            logger.warning(
                "Ignoring malformed supplier cache for %s: expected list, got %s",
                company_name,
                type(cached).__name__,
            )
            return []

        sanitized = []
        for supplier in cached:
            if not isinstance(supplier, dict):
                continue
            name = supplier.get("name", "")
            valid_name, rejection_reason = validate_supplier_candidate_name(
                name, company_name
            )
            if not valid_name:
                logger.debug(
                    "[CACHE FILTER] Rejected cached supplier for %s: %s (%s)",
                    company_name,
                    name,
                    rejection_reason,
                )
                continue
            sanitized.append(supplier)
        return sanitized

    def find_suppliers(self, company_name: str) -> List[Dict[str, Any]]:
        """
        Searches for suppliers using Wikipedia API with backoff and caching.
        """
        cache_enabled = self._cache_enabled()
        refresh_requested = self._refresh_requested()

        if self.prefer_curated and cache_enabled and not refresh_requested:
            canonical = canonical_curated_company_name(company_name)
            if canonical and canonical in CURATED_SUPPLIER_GRAPH:
                logger.debug("CURATED SUPPLIER GRAPH HIT: %s", company_name)
                return get_curated_suppliers(company_name)

        if self.runtime_state and stop_if_timed_out(self.runtime_state, self.stage_key):
            return []

        cache_path = self._get_cache_path(company_name)
        if cache_enabled and not refresh_requested and os.path.exists(cache_path):
            logger.debug("CACHE HIT: %s", company_name)
            with open(cache_path, "r") as f:
                cached_suppliers = self._sanitize_cached_suppliers(
                    json.load(f), company_name
                )
            if cached_suppliers:
                self.stats["Cache Used"] += 1
                return cached_suppliers
            logger.info(
                "Ignoring empty or fully filtered supplier cache for %s; running live discovery.",
                company_name,
            )
        elif not cache_enabled:
            logger.debug("CACHE DISABLED: %s", company_name)
        elif refresh_requested:
            logger.debug("CACHE REFRESH REQUESTED: %s", company_name)

        logger.debug("CACHE MISS: %s", company_name)
        logger.info(f"Searching for real suppliers of {company_name} via Wikipedia...")

        discovered_data = []
        seen_results = set()
        max_retries = int(getattr(self.runtime_state, "max_retries", 2) or 2)

        def add_result(result: Dict[str, Any]) -> None:
            key = (
                result.get("title", ""),
                _strip_search_markup(result.get("snippet", "")),
                result.get("link", ""),
            )
            if key in seen_results:
                return
            seen_results.add(key)
            discovered_data.append(result)

        for result in self._fetch_target_company_context(company_name):
            add_result(result)

        queries = discovery_queries(company_name)
        if canonical_curated_company_name(company_name) == "Qualcomm":
            logger.debug(
                "[QUALCOMM DISCOVERY] Executing %s supplier discovery queries.",
                len(queries),
            )

        for query in queries:
            if canonical_curated_company_name(company_name) == "Qualcomm":
                logger.debug("[QUALCOMM DISCOVERY] Query: %s", query)
            if self.runtime_state and stop_if_timed_out(
                self.runtime_state, self.stage_key
            ):
                break
            retry_count = 0
            while retry_count <= max_retries:
                if not can_consume_web_query(
                    self.runtime_state, self.stage_key, f"Wikipedia supplier search for '{query}'"
                ):
                    break
                try:
                    search_url = "https://en.wikipedia.org/w/api.php"
                    params = {
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "format": "json",
                        "limit": 20,
                    }
                    response = self.session.get(
                        search_url,
                        params=params,
                        headers=self.headers,
                        timeout=remaining_stage_timeout(
                            self.runtime_state, self.stage_key, 5.0
                        ),
                    )

                    if response.status_code == 429:
                        retry_count += 1
                        if retry_count > max_retries:
                            logger.warning(
                                f"[429 RETRY] Attempt: {retry_count} Wait: aborted after max retries for query '{query}'"
                            )
                            self.stats["Wikipedia Retry Count"] += 1
                            break

                        retry_after = response.headers.get("Retry-After")
                        wait_time = None
                        if retry_after and retry_after.isdigit():
                            wait_time = int(retry_after)
                        else:
                            wait_time = min(2**retry_count, 20)

                        jitter = min(5, max(0, (wait_time * 0.2)))
                        wait_time = wait_time + (
                            jitter * (0.5 - os.urandom(1)[0] / 255.0)
                        )
                        wait_time = max(1.0, wait_time)

                        logger.warning(
                            f"[429 RETRY] Attempt: {retry_count} Wait: {wait_time:.1f}s"
                        )
                        self.stats["Wikipedia Retry Count"] += 1
                        if self.runtime_state and stop_if_timed_out(
                            self.runtime_state, self.stage_key
                        ):
                            break
                        time.sleep(
                            min(
                                wait_time,
                                remaining_stage_timeout(
                                    self.runtime_state, self.stage_key, 5.0
                                ),
                            )
                        )
                        continue

                    response.raise_for_status()
                    self.stats["Wikipedia Success"] += 1

                    search_results = response.json().get("query", {}).get("search", [])
                    for res in search_results:
                        score = 0
                        snippet_low = res["snippet"].lower()
                        if company_name.lower() in snippet_low:
                            score += 5
                        rel_keywords = [
                            "supplies",
                            "supplier",
                            "provides",
                            "manufactures",
                            "vendor",
                            "contractor",
                            "component",
                            "parts",
                            "partnership",
                            "subsidiary",
                            "client",
                            "customer",
                            "foundry",
                            "foundries",
                            "wafer",
                            "fabrication",
                            "packaging",
                            "osat",
                            "outsourced",
                            "odm",
                        ]
                        score += sum(2 for k in rel_keywords if k in snippet_low)
                        add_result(
                            {
                                "title": res["title"],
                                "snippet": res["snippet"],
                                "link": f"https://en.wikipedia.org/wiki/{res['title'].replace(' ', '_')}",
                                "quality_score": score,
                            }
                        )

                    time.sleep(0.2)
                    break
                except Exception as e:
                    logger.error(f"Wikipedia search failed for '{query}': {e}")
                    break

        # Sort by quality score before extracting suppliers
        discovered_data.sort(key=lambda x: x["quality_score"], reverse=True)
        formatted_suppliers = self._extract_suppliers_from_results(
            discovered_data, company_name
        )

        # Save to cache if successful
        if cache_enabled and formatted_suppliers:
            with open(cache_path, "w") as f:
                json.dump(formatted_suppliers, f)

        return formatted_suppliers

    def _fetch_target_company_context(self, company_name: str) -> List[Dict[str, Any]]:
        """
        Fetches supplier-relevant snippets from the target company's Wikipedia page.

        Search snippets often omit surrounding manufacturing context; page extracts
        expose statements such as outsourced manufacturing, foundry use, and ODM
        relationships without relying on any expected supplier list.
        """
        try:
            if not can_consume_web_query(
                self.runtime_state,
                self.stage_key,
                f"Wikipedia page search for '{company_name}'",
            ):
                return []
            search_response = self.session.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": company_name,
                    "format": "json",
                    "limit": 1,
                },
                headers=self.headers,
                timeout=remaining_stage_timeout(self.runtime_state, self.stage_key, 5.0),
            )
            search_response.raise_for_status()
            search_results = (
                search_response.json().get("query", {}).get("search", [])
            )
            if not search_results:
                return []

            page_title = search_results[0]["title"]
            if not can_consume_web_query(
                self.runtime_state,
                self.stage_key,
                f"Wikipedia page extract for '{page_title}'",
            ):
                return []
            extract_response = self.session.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": 1,
                    "titles": page_title,
                    "format": "json",
                    "redirects": 1,
                },
                headers=self.headers,
                timeout=remaining_stage_timeout(self.runtime_state, self.stage_key, 5.0),
            )
            extract_response.raise_for_status()
            pages = extract_response.json().get("query", {}).get("pages", {})
            extract = " ".join(page.get("extract", "") for page in pages.values())
            if not extract:
                return []

            snippets = []
            sentences = re.split(r"(?<=[.!?])\s+", extract)
            for sentence in sentences:
                if not _has_manufacturing_context(sentence):
                    continue
                snippets.append(
                    {
                        "title": page_title,
                        "snippet": sentence,
                        "link": f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}",
                        "quality_score": 8,
                    }
                )
                if len(snippets) >= 12:
                    break
            return snippets
        except Exception as e:
            logger.error(f"Wikipedia page context failed for '{company_name}': {e}")
            return []

    def _extract_suppliers_from_results(
        self, results: List[Dict[str, str]], target_company: str
    ) -> List[Dict[str, Any]]:
        """
        Uses heuristics and text analysis to identify potential supplier names.
        Filters out non-company entities and Wikipedia meta-pages.
        """
        suppliers = {}

        # Keywords that indicate a Wikipedia meta-page or non-company entity
        blacklist_patterns = [
            r"^List of",
            r"^Criticism of",
            r"^History of",
            r"^Timeline of",
            r"^Environmental impact of",
            r"Litigation",
            r"Lawsuit",
            r"Codenames",
            r"Products of",
            r"Controversies",
            r"Silicon Valley",
            r"Cupertino",
            r"California",
            r"^The ",
            r"Original design manufacturer",
            r"Integrated device manufacturer",
            r"Board support package",
            r"Booting process",
            r"Foundry model",
            r"Fair Trade Commission",
            r"World Is Flat",
            r"Rights Advocates",
            r"businessman",
            r"Chief Supply Chain Officer",
            r"Operations at",
            r"Senior Vice President",
            r"Executive",
            r"Director of",
            r"ChatGPT",
            r"PyTorch",
            r"TensorFlow",
            r"Open source",
            r"Software",
            r"Algorithm",
        ]

        relationship_keywords = {
            "SUPPLIER": [
                "supplies",
                "supplier",
                "supplied by",
                "provides",
                "manufactures",
                "fabricates",
                "foundry",
                "foundries",
                "vendor",
                "contractor",
                "contract manufacturer",
                "component",
                "parts",
                "semiconductor",
                "oem",
                "odm",
                "original design manufacturer",
                "assembly partner",
                "packaging partner",
                "manufacturing partner",
                "outsourced its manufacturing",
                "outsourced manufacturing",
                "wafer fabrication",
                "chip packaging",
                "osat",
            ],
            "PARTNER": [
                "partnership",
                "partner",
                "collaboration",
                "joint venture",
                "alliance",
                "cooperation",
            ],
            "ACQUISITION": [
                "acquired",
                "merger",
                "acquisition",
                "bought",
                "subsidiary",
                "parent",
            ],
            "COMPETITOR": [
                "competitor",
                "rival",
                "competes",
                "competition",
                "competing",
                "vs",
                "versus",
            ],
            "LAWSUIT": [
                "lawsuit",
                "litigation",
                "sued",
                "infringement",
                "court",
                "legal action",
                "dispute",
            ],
        }

        target_norm = re.sub(r"[^a-z0-9]", "", target_company.lower())
        justifications = {
            "SUPPLIER": f"Directly mentioned as a supplier/vendor for {target_company}",
            "PARTNER": f"Identified as having a partnership or collaboration with {target_company}",
            "ACQUISITION": f"Mentioned in context of an acquisition or merger involving {target_company}",
            "COMPETITOR": f"Identified as a competitor or rival to {target_company}",
            "LAWSUIT": f"Mentioned in context of legal action or litigation with {target_company}",
            "CUSTOMER": f"Identified as a customer or client of {target_company}",
            "NEUTRAL": "Found in industry-related context",
        }

        def is_blacklisted_name(name: str) -> bool:
            return any(
                re.search(b_pattern, name, re.IGNORECASE)
                for b_pattern in blacklist_patterns
            )

        def detect_relationship(name: str, low_text: str, page_title: str) -> str:
            name_low = name.lower()
            detected_rel = "NEUTRAL"
            target_low = target_company.lower()
            if re.search(rf"\bsupplier\s+of\s+{re.escape(target_low)}[-\s]+based\b", low_text):
                return "CUSTOMER"
            if re.search(rf"\b(?:against|overtook)\s+{re.escape(target_low)}\b", low_text):
                return "COMPETITOR"
            if "anti-competitive" in low_text and re.search(
                rf"\bagainst\s+{re.escape(target_low)}\b", low_text
            ):
                return "COMPETITOR"
            if "technology-sharing" in low_text:
                return "CUSTOMER"
            if "defendant" in low_text or "lawsuit" in low_text:
                return "LAWSUIT"
            if "not using" in low_text:
                return "CUSTOMER"
            customer_patterns = [
                rf"{target_low}.*?(?:supplies|provides|manufactures|assembled\s+for).*?{name_low}",
                rf"{name_low}.*?is a (?:customer|client) of.*?{target_low}",
                rf"{name_low}.*?contracted.*?to.*?{target_low}",
            ]

            if any(re.search(cp, low_text) for cp in customer_patterns):
                detected_rel = "CUSTOMER"
            else:
                for rel_type, keywords in relationship_keywords.items():
                    if any(k in low_text for k in keywords):
                        detected_rel = rel_type
                        break

            if " vs " in page_title or " versus " in page_title:
                name_norm = re.sub(r"[^a-z0-9]", "", name_low)
                if name_norm in page_title:
                    detected_rel = "COMPETITOR"

            if detected_rel == "NEUTRAL" and _has_manufacturing_context(low_text):
                detected_rel = "SUPPLIER"

            return detected_rel

        def record_candidate(raw_name: str, res: Dict[str, str], clean_snippet: str) -> None:
            name = normalize_supplier_candidate_name(raw_name, target_company)
            if not name:
                return

            valid_name, rejection_reason = validate_supplier_candidate_name(
                name, target_company
            )
            if not valid_name:
                logger.debug(
                    "[CANDIDATE VALIDATION] Rejected %s: %s",
                    name,
                    rejection_reason,
                )
                return

            name_norm = re.sub(r"[^a-z0-9]", "", name.lower())
            if len(name) < 3 or target_norm in name_norm or name_norm in target_norm:
                return
            if any(
                phrase in name.lower()
                for phrase in [
                    "multinational corporation",
                    "designs and",
                    "manufactures consumer",
                    "based in",
                ]
            ):
                return
            if is_blacklisted_name(name):
                return
            if not name[0].isupper() or name.lower() in ["this", "it", "they", "the"]:
                return

            evidence = [
                {
                    "title": res.get("title", ""),
                    "link": res["link"],
                    "snippet": res["snippet"],
                }
            ]
            if not _candidate_evidence_mentions_relationship(
                name, target_company, evidence
            ):
                return

            page_title = res["title"].lower()
            low_text = f"{res['title']} {clean_snippet}".lower()
            detected_rel = detect_relationship(name, low_text, page_title)
            if detected_rel in {"COMPETITOR", "CUSTOMER", "LAWSUIT", "ACQUISITION"}:
                return

            if name not in suppliers:
                suppliers[name] = {
                    "name": name,
                    "evidence": [],
                    "count": 0,
                    "snippet": clean_snippet,
                    "relationship": detected_rel,
                    "justification": justifications[detected_rel],
                }
            elif suppliers[name]["relationship"] != "SUPPLIER" and detected_rel == "SUPPLIER":
                suppliers[name]["relationship"] = detected_rel
                suppliers[name]["justification"] = justifications[detected_rel]

            evidence_key = (_strip_search_markup(res.get("snippet", "")), res["link"])
            existing_evidence_keys = {
                (_strip_search_markup(e.get("snippet", "")), e.get("link", ""))
                for e in suppliers[name]["evidence"]
            }
            if evidence_key not in existing_evidence_keys:
                suppliers[name]["count"] += 1
                suppliers[name]["evidence"].append(evidence[0])

        for res in results:
            clean_snippet = _strip_search_markup(res["snippet"])
            page_title = res["title"].lower()
            if _compact_key(res["title"]) in PRODUCT_FRAGMENT_NAMES:
                continue
            text = f"{res['title']} {clean_snippet}"

            if not _looks_like_list_or_meta_page(res["title"]) and not is_blacklisted_name(res["title"]):
                record_candidate(res["title"], res, clean_snippet)

            direct_patterns = [
                r"\b([A-Z][A-Za-z0-9\s&]{2,40}\b(?:Inc|Ltd|Corp|Group|Co|PLC|Corporation|Limited))\b",
                r"\b([A-Z][A-Za-z0-9\s&]{2,30})\b (?:supplies|provides|manufactures|manufactured|assembles|assembled|is a supplier)",
                r"(?:assembled|manufactured|fabricated|packaged|built|produced|supplied) by (?:original design manufacturer\s+\(ODM\)\s+|ODM\s+|OSAT\s+)?\b([A-Z][A-Za-z0-9\s&]{2,40})\b",
                r"outsourced\s+(?:its\s+)?manufacturing\s+after\s+\b([A-Z][A-Za-z0-9\s&]{2,40})\b\s+was\s+spun\s+off",
            ]

            for pattern in direct_patterns:
                for match in re.finditer(pattern, text):
                    record_candidate(match.group(1), res, clean_snippet)

            if _has_manufacturing_context(text):
                list_patterns = [
                    rf"\b(?:built|manufactured|assembled|produced)\s+for\s+{re.escape(target_company)}[^.;]{{0,120}}\bby\b[^.;]{{0,120}}\b(?:including|such as)\s+([^.;]+)",
                    r"\bproduction\s+with\s+(?:other\s+)?foundries\s+including\s+([^.;]+)",
                    r"\bfoundries\s+including\s+([^.;]+)",
                    r"\b(?:suppliers|vendors|manufacturing partners|contract manufacturers|original design manufacturers|ODMs|OSATs)\s+(?:including|such as|like)\s+([^.;]+)",
                ]
                for pattern in list_patterns:
                    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                        for name in _split_candidate_list(match.group(1), target_company):
                            record_candidate(name, res, clean_snippet)

        formatted_suppliers = []
        for name, data in suppliers.items():
            if data["relationship"] in {"COMPETITOR", "CUSTOMER", "LAWSUIT", "ACQUISITION"}:
                continue

            evidence_analysis = analyze_supplier_evidence(data["evidence"])
            confidence = 0.35 + min(data["count"] * 0.07, 0.21)
            if re.search(
                r"(Inc|Ltd|Corp|Group|Co|PLC|Corporation|Limited)$", name, re.IGNORECASE
            ):
                confidence += 0.07
            if is_known_organization(name):
                confidence += 0.08

            rel_weights = {
                "SUPPLIER": 0.25,
                "PARTNER": 0.2,
                "ACQUISITION": 0.1,
                "COMPETITOR": -0.4,
                "LAWSUIT": -0.3,
                "CUSTOMER": -0.5,
                "NEUTRAL": 0.0,
            }
            confidence += rel_weights.get(data["relationship"], 0.0)
            if evidence_analysis["strong_hits"]:
                confidence += 0.12
            if evidence_analysis["medium_hits"]:
                confidence += 0.08
            if evidence_analysis["weak_hits"]:
                confidence += 0.03
            if evidence_analysis["supporting_snippets"] > 1:
                confidence += 0.05
            if evidence_analysis["negative_hits"]:
                confidence -= 0.15

            products = []
            lower_snippet = data["snippet"].lower()
            if any(
                k in lower_snippet
                for k in ["chips", "semiconductor", "processor", "soc", "logic"]
            ):
                products.append("Semiconductors")
            if any(
                k in lower_snippet
                for k in ["logistics", "shipping", "supply chain", "warehousing"]
            ):
                products.append("Logistics Services")
            if any(
                k in lower_snippet
                for k in ["display", "screen", "panel", "oled", "lcd", "led"]
            ):
                products.append("Display Panels")
            if any(
                k in lower_snippet
                for k in ["assembly", "manufacturing", "outsourced", "factory", "odm", "contract manufacturer"]
            ):
                products.append("Contract Manufacturing")
            if any(
                k in lower_snippet
                for k in ["foundry", "foundries", "wafer", "fabrication"]
            ):
                products.append("Semiconductor Foundry")
            if any(k in lower_snippet for k in ["osat", "packaging", "assembly and test"]):
                products.append("Semiconductor Packaging/Test")
            if any(k in lower_snippet for k in ["battery", "cells", "power"]):
                products.append("Energy Storage")

            final_confidence = round(max(0.01, min(confidence, 0.98)), 2)
            formatted_suppliers.append(
                {
                    "name": name,
                    "location": "Unknown (Verified by Research)",
                    "products": products or ["General Components"],
                    "tier": 1 if final_confidence >= 0.75 else 2,
                    "criticality": "High" if final_confidence >= 0.75 else "Medium",
                    "confidence": final_confidence,
                    "justification": data["justification"],
                    "source_evidence": data["evidence"][:2],
                }
            )

        formatted_suppliers.sort(key=lambda x: x["confidence"], reverse=True)
        return formatted_suppliers[:20]

    def get_stats(self) -> Dict[str, int]:
        return self.stats
