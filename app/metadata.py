"""Reads technical info + embedded metadata from audio files.

WAV/BWF files are parsed directly (fast, no audio decoding):
  fmt  -> channels, sample rate, bit depth
  bext -> description
  LIST/INFO -> title, comment, keywords, genre
  iXML -> Soundminer/UCS fields (CATEGORY, SUBCATEGORY, KEYWORDS, ...)
Other formats (AIFF, FLAC, OGG, MP3) go through libsndfile.
"""
import html
import os
import re
import struct

from . import ucs

AUDIO_EXT = {".wav", ".wave", ".bwf", ".aif", ".aiff", ".aifc", ".flac", ".ogg", ".mp3"}

IXML_FIELDS = ("FXNAME", "CATEGORY", "SUBCATEGORY", "CATID", "KEYWORDS",
               "DESCRIPTION", "LIBRARY", "TRACKTITLE", "NOTE")


def _txt(b):
    b = b.split(b"\x00", 1)[0]
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return b.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return ""


def _parse_ixml(text):
    out = {}
    for tag in IXML_FIELDS:
        m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), text, re.S | re.I)
        if m:
            v = html.unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1), flags=re.S)).strip()
            if v:
                out[tag] = v
    return out


def read_wav(path):
    info = {}
    with open(path, "rb") as f:
        hdr = f.read(12)
        if len(hdr) < 12 or hdr[:4] not in (b"RIFF", b"RF64", b"BW64") or hdr[8:12] != b"WAVE":
            return None
        fsize = os.fstat(f.fileno()).st_size
        ds64 = None
        while True:
            ch = f.read(8)
            if len(ch) < 8:
                break
            cid = ch[:4]
            size = struct.unpack("<I", ch[4:])[0]
            start = f.tell()
            if cid == b"ds64":
                d = f.read(min(size, 28))
                if len(d) >= 16:
                    ds64 = struct.unpack("<Q", d[8:16])[0]
            elif cid == b"fmt ":
                d = f.read(min(size, 40))
                if len(d) >= 16:
                    tag, chn, sr, _br, align, bits = struct.unpack("<HHIIHH", d[:16])
                    if tag == 0xFFFE and len(d) >= 26:
                        tag = struct.unpack("<H", d[24:26])[0]
                    info.update(channels=chn, samplerate=sr, align=align,
                                bits=f"{bits}f" if tag == 3 else str(bits))
            elif cid == b"data":
                if size == 0xFFFFFFFF and ds64:
                    size = ds64
                info["data_size"] = size
            elif cid == b"bext":
                d = f.read(min(size, 256))
                info["bext_desc"] = _txt(d)
            elif cid == b"LIST":
                d = f.read(min(size, 1 << 16))
                if d[:4] == b"INFO":
                    p = 4
                    while p + 8 <= len(d):
                        sid = d[p:p + 4].decode("latin-1")
                        ss = struct.unpack("<I", d[p + 4:p + 8])[0]
                        info["INFO_" + sid] = _txt(d[p + 8:p + 8 + ss])
                        p += 8 + ss + (ss & 1)
            elif cid == b"iXML":
                d = f.read(min(size, 1 << 20))
                info["ixml"] = _parse_ixml(_txt(d))
            nxt = start + size + (size & 1)
            if nxt > fsize:
                break
            f.seek(nxt)
    if "samplerate" in info and info.get("align") and "data_size" in info:
        info["duration"] = info["data_size"] / info["align"] / info["samplerate"]
    return info


SUBTYPE_BITS = {"PCM_S8": "8", "PCM_U8": "8", "PCM_16": "16", "PCM_24": "24",
                "PCM_32": "32", "FLOAT": "32f", "DOUBLE": "64f"}


def read_file(path, library_root):
    """Returns a dict ready to be stored in the `sounds` table."""
    stem, ext = os.path.splitext(os.path.basename(path))
    ext = ext.lower()
    tech, ixml = {}, {}
    if ext in (".wav", ".wave", ".bwf"):
        try:
            tech = read_wav(path) or {}
        except OSError:
            tech = {}
        ixml = tech.get("ixml", {})
    if "duration" not in tech:
        try:
            import soundfile as sf
            i = sf.info(path)
            tech.update(channels=i.channels, samplerate=i.samplerate,
                        duration=i.duration, bits=SUBTYPE_BITS.get(i.subtype, ""))
        except Exception:
            pass

    u = ucs.parse_filename(stem)
    rel = os.path.relpath(path, library_root).replace("\\", "/")  # chemin relatif portable
    folders = [p for p in os.path.dirname(rel).split("/") if p]

    catid = ixml.get("CATID") or u.get("catid")
    cat = ixml.get("CATEGORY") or u.get("category")
    sub = ixml.get("SUBCATEGORY")
    if not sub and ixml.get("CATID"):
        sub = ucs.split_catid(ixml["CATID"])[1]
    sub = sub or u.get("subcategory")
    if not cat and folders:  # fallback: folder structure
        cat = folders[0]
        sub = sub or (folders[1] if len(folders) > 1 else None)

    name = (ixml.get("FXNAME") or u.get("fxname") or tech.get("INFO_INAM")
            or ixml.get("TRACKTITLE") or stem)
    desc = (ixml.get("DESCRIPTION") or tech.get("bext_desc") or tech.get("INFO_ICMT")
            or ixml.get("NOTE") or "")
    if desc.strip().lower() == name.strip().lower():
        desc = ""
    st = os.stat(path)
    return {
        "path": path,
        "relpath": rel,
        "filename": os.path.basename(path),
        "name": name,
        "description": desc,
        "keywords": ixml.get("KEYWORDS") or tech.get("INFO_IKEY") or "",
        "category": (cat or "").strip() or None,
        "subcategory": (sub or "").strip() or None,
        "catid": catid,
        "source": ixml.get("LIBRARY") or u.get("source") or "",
        "duration": tech.get("duration"),
        "channels": tech.get("channels"),
        "samplerate": tech.get("samplerate"),
        "bits": tech.get("bits", ""),
        "format": ext.lstrip(".").upper().replace("WAVE", "WAV").replace("AIFF", "AIF"),
        "size": st.st_size,
        "mtime": st.st_mtime,
        "folder": " ".join(folders),
    }
