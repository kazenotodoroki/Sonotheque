"""Universal Category System (UCS) helpers.

Most commercial SFX libraries (BOOM, Pro Sound Effects, Sonniss...) name their
files following UCS:  CatID_FXName_CreatorID_SourceID.wav
e.g.  ANMLInsc_Fly Buzz Pass By_B00M_BO.wav

The CatID is the main category abbreviation followed by a subcategory
abbreviation. When the file carries embedded metadata (iXML / Soundminer),
that metadata always wins; this module is only the fallback.
"""
import re

# Main UCS category abbreviations -> category name
CATEGORIES = {
    "AERO": "AIRCRAFT", "AIR": "AIR", "ALRM": "ALARMS", "AMB": "AMBIENCE",
    "ANML": "ANIMALS", "ARCHIVED": "ARCHIVED", "BEEP": "BEEPS", "BELL": "BELLS",
    "BIRD": "BIRDS", "BLLT": "BULLETS", "BOAT": "BOATS", "BRKN": "BREAKING",
    "BUBL": "BUBBLES", "CERM": "CERAMICS", "CHAIN": "CHAINS", "CHEM": "CHEMICALS",
    "CLOCK": "CLOCKS", "CLOTH": "CLOTH", "COMM": "COMMUNICATIONS",
    "COMP": "COMPUTERS", "CREA": "CREATURES", "CRWD": "CROWDS", "CROWD": "CROWDS",
    "DSGN": "DESIGNED", "DEST": "DESTRUCTION", "DIRT": "DIRT & SAND",
    "DOOR": "DOORS", "DRWR": "DRAWERS", "ELEC": "ELECTRICITY", "EQUIP": "EQUIPMENT",
    "EXPL": "EXPLOSIONS", "FART": "FARTS", "FGHT": "FIGHT", "FIRE": "FIRE",
    "FIREWRK": "FIREWORKS", "FOLY": "FOLEY", "FOOD": "FOOD & DRINK",
    "FEET": "FOOTSTEPS", "GAME": "GAMES", "GEOT": "GEOTHERMAL", "GLAS": "GLASS",
    "GORE": "GORE", "GUN": "GUNS", "GUNS": "GUNS", "HORN": "HORNS", "HMN": "HUMAN",
    "ICE": "ICE", "LASR": "LASERS", "LETHR": "LEATHER", "LIQ": "LIQUID & MUD",
    "MACH": "MACHINES", "MAGC": "MAGIC", "MECH": "MECHANICAL", "METL": "METAL",
    "MOTR": "MOTORS", "MOVE": "MOVEMENT", "MUSC": "MUSICAL",
    "NATDIS": "NATURAL DISASTER", "OBJ": "OBJECTS", "PAPR": "PAPER",
    "PLAS": "PLASTIC", "RAIN": "RAIN", "ROBO": "ROBOTS", "ROCK": "ROCKS",
    "ROPE": "ROPE", "RUBR": "RUBBER", "SCI": "SCIFI", "SNOW": "SNOW",
    "SPRT": "SPORTS", "SWSH": "SWOOSHES", "SWCH": "SWITCHES", "TOOL": "TOOLS",
    "TOON": "CARTOON", "TOY": "TOYS", "TRAIN": "TRAINS", "UI": "USER INTERFACE",
    "VEH": "VEHICLES", "VOX": "VOICES", "WATR": "WATER", "WEAP": "WEAPONS",
    "WHSH": "WHOOSHES", "WIND": "WIND", "WNDW": "WINDOWS", "WOOD": "WOOD",
}
_SORTED = sorted(CATEGORIES, key=len, reverse=True)
_CATID_RE = re.compile(r"^[A-Z]{2,}[A-Za-z0-9]*$")


def split_catid(catid):
    """'ANMLInsc' -> ('ANIMALS', 'Insc'). Returns (None, None) if unknown."""
    if not catid:
        return None, None
    for abbr in _SORTED:
        if catid.upper().startswith(abbr):
            rest = catid[len(abbr):]
            return CATEGORIES[abbr], (rest or None)
    return None, None


def parse_filename(stem):
    """Parse a UCS filename stem. Returns dict (possibly empty)."""
    parts = stem.split("_")
    if len(parts) < 2 or not _CATID_RE.match(parts[0]):
        return {}
    cat, sub = split_catid(parts[0])
    if not cat:
        return {}
    out = {"catid": parts[0], "category": cat, "subcategory": sub,
           "fxname": parts[1].strip()}
    if len(parts) >= 4:
        out["source"] = parts[3].strip()
    return out
