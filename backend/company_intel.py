"""
Company Intelligence Engine for VaultMind
==========================================
Pre-extracts clues from job descriptions and cross-references against
a known company database. Does the heavy analytical lifting in Python
so small local models only need to format results, not reason about them.
"""

import re
from urllib.parse import urlparse
from dataclasses import dataclass, field


# ── Known Company Database ──────────────────────────────────────
# Key: lowercase company name
# Value: dict with location, industry, size, keywords that would appear in descriptions

@dataclass
class CompanyProfile:
    name: str
    location: str
    industry: str
    size: str = ""
    keywords: list = field(default_factory=list)
    description: str = ""


# Orange County / SoCal focused — expand as needed
COMPANY_DB: dict[str, CompanyProfile] = {}

def _add(name, location, industry, size="", keywords=None, description=""):
    COMPANY_DB[name.lower()] = CompanyProfile(
        name=name, location=location, industry=industry,
        size=size, keywords=keywords or [], description=description
    )

# ── Medical Devices ──
_add("Johnson & Johnson Vision", "Santa Ana/Irvine, CA", "Medical Devices - Ophthalmology",
     "Fortune 50", ["vision", "optical", "eye", "surgery", "ophthalmology", "medical device", "contact lens"])
_add("Alcon", "Lake Forest, CA / Fort Worth, TX", "Medical Devices - Ophthalmology",
     "Fortune 500", ["vision", "eye", "surgical", "ophthalmology", "cataract", "medical device"])
_add("Edwards Lifesciences", "Irvine, CA", "Medical Devices - Cardiovascular",
     "Fortune 500", ["heart valve", "cardiovascular", "transcatheter", "hemodynamic", "medical device"])
_add("Masimo", "Irvine, CA", "Medical Devices - Patient Monitoring",
     "Public", ["pulse oximetry", "patient monitoring", "noninvasive", "medical device", "hospital"])
_add("ICU Medical", "San Clemente, CA", "Medical Devices - Infusion",
     "Public", ["infusion", "IV", "medical device", "hospital", "pharmacy"])
_add("Glaukos", "San Clemente/Laguna Hills, CA", "Medical Devices - Ophthalmology",
     "Public", ["glaucoma", "eye", "micro-invasive", "ophthalmology", "iStent"])
_add("Abbott Medical", "Irvine, CA (formerly St. Jude)", "Medical Devices",
     "Fortune 100", ["neuromodulation", "cardiac", "arrhythmia", "medical device"])

# ── IoT / Retail Tech ──
_add("Sensormatic Solutions (Johnson Controls)", "Boca Raton, FL / offices in OC", "IoT - Retail Loss Prevention",
     "Fortune 100 parent", ["loss prevention", "retail", "IoT", "analytics", "shrink", "inventory"])
_add("InVue", "Charlotte, NC / offices in OC", "IoT - Retail Security",
     "Private", ["retail", "loss prevention", "merchandise protection", "IoT"])
_add("Checkpoint Systems", "Thorofare, NJ / offices in SoCal", "IoT - Retail Loss Prevention",
     "Division of CCL", ["loss prevention", "retail", "EAS", "RFID", "inventory"])
_add("Tyco Retail Solutions", "Boca Raton, FL / SoCal", "IoT - Retail Loss Prevention",
     "Part of Johnson Controls", ["loss prevention", "retail", "IoT", "analytics", "shrink"])
_add("SureFire", "Fountain Valley, CA", "Defense / Lighting",
     "Private", ["flashlight", "weapon light", "defense", "tactical"])

# ── EV / Automotive ──
_add("Rivian", "Irvine, CA", "Electric Vehicles",
     "Public", ["EV", "electric vehicle", "autonomous", "truck", "R1T", "R1S", "adventure"])
_add("Karma Automotive", "Irvine, CA", "Electric Vehicles",
     "Private", ["EV", "electric vehicle", "luxury", "hybrid", "Revero"])
_add("Hyundai/Kia Design Center", "Irvine, CA", "Automotive",
     "Fortune 500 parent", ["automotive", "design", "vehicle", "EV", "AV"])
_add("Fisker", "Manhattan Beach, CA (was in OC)", "Electric Vehicles",
     "Bankrupt/Dissolved", ["EV", "electric vehicle", "Ocean", "sustainable"])
_add("Canoo", "Justin, TX (was in Torrance/OC)", "Electric Vehicles",
     "Public (struggling)", ["EV", "electric vehicle", "lifestyle vehicle", "subscription"])

# ── Tech / SaaS ──
_add("Kajabi", "Irvine, CA", "Creator Economy / SaaS",
     "Venture-backed", ["creator", "monetization", "knowledge commerce", "online course", "coaching"])
_add("Ephesoft", "Irvine, CA", "Document Processing / SaaS",
     "Private", ["document", "capture", "intelligent", "OCR", "automation"])
_add("Cylance (BlackBerry)", "Irvine, CA", "Cybersecurity",
     "Acquired by BlackBerry", ["AI", "cybersecurity", "endpoint", "prevention", "machine learning"])
_add("Alteryx", "Irvine, CA", "Data Analytics / SaaS",
     "Public", ["analytics", "data science", "automation", "self-service", "data"])
_add("Five9", "San Ramon, CA / Irvine office", "Cloud Contact Center",
     "Public", ["contact center", "cloud", "CCaaS", "customer experience"])
_add("Acorns", "Irvine, CA", "Fintech - Investing",
     "Venture-backed / SPAC", ["investing", "micro-investing", "wealth", "spare change", "financial"])
_add("SoFi", "San Francisco, CA / offices nationally", "Fintech",
     "Public", ["fintech", "lending", "investing", "banking", "student loan"])
_add("Blizzard Entertainment", "Irvine, CA", "Gaming",
     "Part of Microsoft", ["gaming", "World of Warcraft", "Diablo", "Overwatch", "Hearthstone"])
_add("Anduril Industries", "Costa Mesa, CA", "Defense Tech",
     "Venture-backed unicorn", ["defense", "autonomous", "surveillance", "AI", "Lattice"])

# ── Enterprise / Hardware ──
_add("Western Digital", "Irvine/San Jose, CA", "Data Storage",
     "Fortune 500", ["storage", "hard drive", "SSD", "flash", "data center"])
_add("Broadcom", "Irvine/San Jose, CA", "Semiconductors",
     "Fortune 500", ["semiconductor", "chip", "networking", "broadband", "wireless"])
_add("Samsung Semiconductor", "San Jose, CA / Austin, TX", "Semiconductors",
     "Fortune Global 50 parent", ["semiconductor", "memory", "NAND", "DRAM", "foundry"])
_add("Verizon Digital Media", "Irvine, CA (now Edgecast/Edgio)", "CDN/Media Tech",
     "Fortune 50 parent", ["CDN", "streaming", "video", "edge", "media"])

# ── Home & Lifestyle ──
_add("Lifetime Brands", "Garden City, NY / SoCal offices", "Home & Lifestyle Products",
     "Public", ["home", "lifestyle", "brands", "housewares", "kitchen", "tabletop"])
_add("Spectrum Brands", "Middleton, WI / SoCal", "Home & Lifestyle Products",
     "Public", ["home", "garden", "pet", "personal care", "hardware"])
_add("Trader Joe's (corporate)", "Monrovia, CA", "Grocery Retail",
     "Private", ["grocery", "retail", "food", "organic"])
_add("Taco Bell (Yum! Brands)", "Irvine, CA", "Fast Food / QSR",
     "Fortune 500 parent", ["restaurant", "fast food", "QSR", "digital ordering", "mobile app"])

# ── Telematics / GPS ──
_add("CalAmp", "Irvine, CA", "Telematics / IoT",
     "Public", ["telematics", "GPS", "fleet", "tracking", "IoT", "connected vehicle"])
_add("Spireon (now Solera)", "Irvine, CA", "Telematics / IoT",
     "Private equity backed", ["telematics", "GPS", "fleet", "tracking", "LoJack", "vehicle intelligence"])
_add("Vyncs", "Irvine, CA", "Telematics / Connected Car",
     "Private", ["telematics", "GPS", "OBD", "connected car", "fleet"])

# ── More OC Tech ──
_add("Irvine Company", "Irvine, CA", "Real Estate",
     "Private", ["real estate", "property", "office", "apartment", "retail", "community"])
_add("Pacific Life", "Newport Beach, CA", "Insurance / Financial Services",
     "Fortune 500", ["insurance", "annuity", "retirement", "financial", "wealth"])
_add("Ingram Micro", "Irvine, CA", "IT Distribution",
     "Private (Platinum Equity)", ["distribution", "technology", "cloud", "lifecycle", "commerce"])
_add("Kia America", "Irvine, CA", "Automotive",
     "Fortune 500 parent", ["automotive", "electric", "vehicle", "mobility"])
_add("Mazda North America", "Irvine, CA", "Automotive",
     "Public (Japan)", ["automotive", "vehicle", "skyactiv", "CX"])


# ── Clue Extraction Engine ─────────────────────────────────────

@dataclass
class ExtractedClue:
    category: str       # "client_mention", "industry", "location", "size", "product"
    text: str           # The actual text from the description
    confidence: float   # 0.0 - 1.0


def extract_clues(description: str) -> list[ExtractedClue]:
    """Extract identifiable clues from a job description."""
    clues = []

    # Direct client mentions ("Our client...")
    for m in re.finditer(r'((?:Our|The|My)\s+client[^.]{10,200}\.)', description, re.IGNORECASE):
        clues.append(ExtractedClue("client_mention", m.group(1).strip(), 0.9))

    # Company type descriptors
    for m in re.finditer(
        r'((?:A|An)\s+(?:fast-growing|leading|well-established|venture-backed|Fortune\s*\d+|'
        r'publicly traded|privately held|private|global|top-tier|innovative|mission-driven|'
        r'rapidly growing|high-growth|established|award-winning)[^.]{10,200}\.)',
        description, re.IGNORECASE
    ):
        clues.append(ExtractedClue("company_type", m.group(1).strip(), 0.7))

    # Industry keywords
    industry_patterns = [
        (r'medical device', "Medical Devices"),
        (r'optical surgery|ophthalmolog|vision.*(?:eye|surgery|lens)', "Medical Devices - Ophthalmology"),
        (r'fintech|financial technology', "Fintech"),
        (r'(?:e-commerce|ecommerce)', "E-Commerce"),
        (r'SaaS', "SaaS"),
        (r'gaming|video game', "Gaming"),
        (r'(?:EV|electric vehicle|autonomous.*vehicle)', "Electric Vehicles / Autonomous"),
        (r'telematics|GPS tracking|fleet', "Telematics / GPS"),
        (r'creator.*(?:monetiz|platform|economy)', "Creator Economy"),
        (r'loss prevention|retail.*(?:security|analytics|shrink)', "Retail Tech / Loss Prevention"),
        (r'IoT|internet of things', "IoT"),
        (r'cybersecurity|information security', "Cybersecurity"),
        (r'defense|military|tactical', "Defense"),
        (r'biotech|pharmaceutical|pharma', "Biotech / Pharma"),
        (r'insurance|annuit|underwriting', "Insurance"),
        (r'real estate|property management', "Real Estate"),
        (r'home.*(?:brand|lifestyle|housewares)', "Home & Lifestyle"),
        (r'semiconductor|chip|foundry', "Semiconductors"),
        (r'retail|(?:brick and mortar|storefront)', "Retail"),
    ]
    for pattern, industry in industry_patterns:
        if re.search(pattern, description, re.IGNORECASE):
            # Get surrounding context
            m = re.search(f'([^.]*{pattern}[^.]*\\.)', description, re.IGNORECASE)
            ctx = m.group(1).strip() if m else industry
            clues.append(ExtractedClue("industry", f"{industry}: {ctx[:150]}", 0.8))

    # Location clues
    location_patterns = [
        r'(?:based|located|headquartered)\s+in\s+([^,.]{5,60})',
        r'(South(?:ern)?\s+Orange\s+County)',
        r'(North(?:ern)?\s+San\s+Diego)',
        r'((?:Lake Forest|Irvine|Newport Beach|Foothill Ranch|Tustin|Santa Ana|'
        r'Costa Mesa|Fountain Valley|San Clemente|Laguna|Los Alamitos|Huntington Beach|'
        r'Anaheim|Orange|Mission Viejo|Aliso Viejo|Dana Point|Rancho Santa Margarita),'
        r'\s*(?:CA|California)?)',
    ]
    for pattern in location_patterns:
        for m in re.finditer(pattern, description, re.IGNORECASE):
            clues.append(ExtractedClue("location", m.group(1).strip() if m.lastindex else m.group(0).strip(), 0.6))

    # Size / funding clues
    size_patterns = [
        r'(Fortune\s*\d+)',
        r'((?:Series\s+[A-F]|IPO|publicly\s+traded|venture[\s-]backed|unicorn))',
        r'(\$[\d,.]+\s*(?:billion|million|B|M)\s+(?:revenue|valuation|company|ARR))',
        r'(one of the (?:largest|biggest|top)\s+[^.]{10,80})',
        r'((?:\d{1,3}[,.]?\d{3})\+?\s+employees)',
    ]
    for pattern in size_patterns:
        for m in re.finditer(pattern, description, re.IGNORECASE):
            clues.append(ExtractedClue("size", m.group(1).strip(), 0.7))

    # Product / service clues
    for m in re.finditer(
        r'(?:builds?|develops?|creates?|provides?|offers?|specializ\w+\s+in)\s+([^.]{10,120}\.)',
        description, re.IGNORECASE
    ):
        clues.append(ExtractedClue("product", m.group(1).strip(), 0.5))

    # Salary / comp
    for m in re.finditer(r'(\$[\d,]+[kK]?\s*[-–]\s*\$[\d,]+[kK]?)', description):
        clues.append(ExtractedClue("compensation", m.group(1), 0.3))
    for m in re.finditer(r'(\$\d+/hr\s*[-–]\s*\$\d+/hr)', description):
        clues.append(ExtractedClue("compensation", m.group(1), 0.3))

    return clues


def match_company(clues: list[ExtractedClue]) -> list[tuple[str, float, str]]:
    """Match extracted clues against the company database.
    Returns list of (company_name, confidence_score, reason)."""

    scores: dict[str, tuple[float, list[str]]] = {}

    for clue in clues:
        clue_lower = clue.text.lower()

        for key, profile in COMPANY_DB.items():
            match_reasons = []
            match_score = 0.0

            # Check keyword matches
            for kw in profile.keywords:
                if kw.lower() in clue_lower:
                    match_score += 0.15 * clue.confidence
                    match_reasons.append(f"keyword '{kw}'")

            # Check location matches
            if clue.category == "location":
                loc_lower = profile.location.lower()
                clue_words = clue_lower.split()
                for word in clue_words:
                    if len(word) > 3 and word in loc_lower:
                        match_score += 0.2 * clue.confidence
                        match_reasons.append(f"location '{word}'")
                        break

            # Check industry matches
            if clue.category == "industry":
                if profile.industry.lower().split(" - ")[0] in clue_lower or \
                   profile.industry.lower() in clue_lower:
                    match_score += 0.25 * clue.confidence
                    match_reasons.append(f"industry '{profile.industry}'")

            # Check size matches
            if clue.category == "size" and profile.size:
                if profile.size.lower() in clue_lower:
                    match_score += 0.1 * clue.confidence
                    match_reasons.append(f"size '{profile.size}'")

            if match_score > 0:
                if key not in scores:
                    scores[key] = (0.0, [])
                old_score, old_reasons = scores[key]
                scores[key] = (old_score + match_score, old_reasons + match_reasons)

    # Sort by score, return top matches
    results = []
    for key, (score, reasons) in sorted(scores.items(), key=lambda x: x[1][0], reverse=True):
        profile = COMPANY_DB[key]
        # Deduplicate reasons
        unique_reasons = list(dict.fromkeys(reasons))
        confidence = min(score, 1.0)
        conf_label = "High" if confidence > 0.5 else "Medium" if confidence > 0.25 else "Low"
        results.append((
            profile.name,
            confidence,
            f"{conf_label} — matched on: {', '.join(unique_reasons[:5])}. "
            f"({profile.industry}, {profile.location}, {profile.size})"
        ))

    return results[:5]  # Top 5 matches


def analyze_job_listing(title: str, description: str, url: str) -> dict:
    """Full analysis pipeline for a single job listing.
    Returns a pre-structured result the model can simply format."""

    clues = extract_clues(description)
    matches = match_company(clues)

    # Build the pre-analyzed result
    result = {
        "title": title,
        "url": url,
        "clues": [{"category": c.category, "text": c.text[:200], "confidence": c.confidence}
                  for c in clues if c.confidence > 0.4],
        "likely_companies": [
            {"name": name, "confidence": conf, "reasoning": reason}
            for name, conf, reason in matches
        ],
        "top_match": matches[0][0] if matches else "Unknown — insufficient clues",
        "top_confidence": matches[0][1] if matches else 0.0,
    }

    return result


def analyze_agency_listings(listings: list[dict]) -> str:
    """Analyze a batch of agency job listings and return a pre-structured
    text block that a small model can format without needing to reason."""

    output = "PRE-ANALYZED CLIENT INTELLIGENCE REPORT\n"
    output += "=" * 50 + "\n\n"
    output += "The following analysis was performed programmatically by cross-referencing\n"
    output += "clues in each job description against a database of known companies.\n"
    output += "The model's job is ONLY to format this nicely — all analysis is done.\n\n"

    for i, listing in enumerate(listings, 1):
        title = listing.get("title", "Unknown")[:80]
        desc = listing.get("description", "")
        url = listing.get("url", "")

        if not desc:
            output += f"JOB #{i}: {title}\n"
            output += f"URL: {url}\n"
            output += "Analysis: No description available to analyze.\n\n"
            continue

        analysis = analyze_job_listing(title, desc, url)

        output += f"{'─' * 50}\n"
        output += f"JOB #{i}: {title}\n"
        output += f"URL: {url}\n\n"

        if analysis["clues"]:
            output += "KEY CLUES FOUND:\n"
            for clue in analysis["clues"][:4]:
                output += f"  • [{clue['category'].upper()}] {clue['text']}\n"
            output += "\n"

        if analysis["likely_companies"]:
            output += "LIKELY CLIENT COMPANIES:\n"
            for j, company in enumerate(analysis["likely_companies"][:3], 1):
                output += f"  {j}. {company['name']} — {company['reasoning']}\n"
            output += f"\n→ BEST GUESS: {analysis['top_match']}\n"
        else:
            output += "LIKELY CLIENT: Could not determine — insufficient identifying clues.\n"
            output += "  (Job may be a direct hire for the agency or lacks specific client details)\n"

        output += "\n"

    return output
