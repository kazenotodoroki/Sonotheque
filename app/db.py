import os
import re
import sqlite3
import time
import zlib

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS libraries(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS sounds(
    id INTEGER PRIMARY KEY,
    library_id INTEGER NOT NULL,
    path TEXT NOT NULL UNIQUE, relpath TEXT, filename TEXT,
    name TEXT, description TEXT, keywords TEXT,
    category TEXT, subcategory TEXT, catid TEXT, source TEXT,
    duration REAL, channels INTEGER, samplerate INTEGER, bits TEXT, format TEXT,
    size INTEGER, mtime REAL);
CREATE INDEX IF NOT EXISTS ix_sounds_lib ON sounds(library_id);
CREATE INDEX IF NOT EXISTS ix_sounds_rel ON sounds(library_id, relpath);
CREATE INDEX IF NOT EXISTS ix_sounds_cat ON sounds(category, subcategory);
CREATE INDEX IF NOT EXISTS ix_sounds_name ON sounds(name COLLATE NOCASE);
CREATE VIRTUAL TABLE IF NOT EXISTS sounds_fts USING fts5(
    name, filename, description, keywords, category, subcategory, source, folder,
    tokenize = 'unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS wave(id INTEGER PRIMARY KEY, data BLOB);
DROP TABLE IF EXISTS peaks;
"""

FIELDS = ("library_id", "path", "relpath", "filename", "name", "description", "keywords",
          "category", "subcategory", "catid", "source", "duration", "channels",
          "samplerate", "bits", "format", "size", "mtime")
# champs transportés dans un index .sonolib (chemins relatifs, sans library_id/path)
PORTABLE = ("filename", "name", "description", "keywords", "category", "subcategory", "catid",
            "source", "duration", "channels", "samplerate", "bits", "format", "size", "mtime")
INDEX_VERSION = 1


def connect(path):
    con = sqlite3.connect(path, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA cache_size=-65536")
    con.executescript(SCHEMA)
    return con


def folder_words(relpath):
    return " ".join(p for p in relpath.replace("\\", "/").split("/")[:-1] if p)


# ---------------------------------------------------------------- waveforms
# 600 colonnes en 8 bits compressées : ~0,3–0,6 Ko par son (≈ 250 Mo pour 500 000 sons)
def encode_wave(peaks):
    q = np.clip(np.round(np.asarray(peaks, np.float32) * 255), 0, 255).astype(np.uint8)
    return zlib.compress(q.tobytes(), 6)


def decode_wave(blob):
    return np.frombuffer(zlib.decompress(blob), np.uint8).astype(np.float32) / 255.0


# ---------------------------------------------------------------- writes
def upsert_sound(con, lib_id, meta, existing_id=None, keep_wave=False):
    meta = dict(meta, library_id=lib_id)
    vals = [meta.get(k) for k in FIELDS]
    if existing_id:
        con.execute("UPDATE sounds SET %s WHERE id=?" % ",".join(f"{k}=?" for k in FIELDS),
                    vals + [existing_id])
        con.execute("DELETE FROM sounds_fts WHERE rowid=?", (existing_id,))
        if not keep_wave:
            con.execute("DELETE FROM wave WHERE id=?", (existing_id,))
        sid = existing_id
    else:
        cur = con.execute("INSERT INTO sounds(%s) VALUES (%s)" % (",".join(FIELDS), ",".join("?" * len(FIELDS))), vals)
        sid = cur.lastrowid
    con.execute(
        "INSERT INTO sounds_fts(rowid,name,filename,description,keywords,category,subcategory,source,folder)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (sid, meta["name"], (meta["filename"] or "").replace("_", " "), meta["description"],
         meta["keywords"], meta["category"], meta["subcategory"], meta["source"],
         meta.get("folder") or folder_words(meta.get("relpath") or "")))
    return sid


def delete_sounds(con, ids):
    ids = list(ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = ",".join("?" * len(chunk))
        for t, col in (("sounds", "id"), ("sounds_fts", "rowid"), ("wave", "id")):
            con.execute(f"DELETE FROM {t} WHERE {col} IN ({q})", chunk)


def remove_library(con, lib_id):
    ids = [r[0] for r in con.execute("SELECT id FROM sounds WHERE library_id=?", (lib_id,))]
    delete_sounds(con, ids)
    con.execute("DELETE FROM libraries WHERE id=?", (lib_id,))
    con.commit()


# ---------------------------------------------------------------- portable index
def read_index_meta(path):
    """Infos d'un fichier .sonolib, ou None s'il est illisible."""
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        meta = dict(c.execute("SELECT k, v FROM meta"))
        c.close()
        if int(meta.get("version", 0)) > INDEX_VERSION:
            return None
        return meta
    except Exception:
        return None


def export_index(con, lib_id, dest, with_waves, cancelled=lambda: False):
    name, root = con.execute("SELECT name, path FROM libraries WHERE id=?", (lib_id,)).fetchone()
    tmp = dest + ".part"
    if os.path.exists(tmp):
        os.remove(tmp)
    con.commit()
    con.execute("ATTACH DATABASE ? AS x", (tmp,))
    try:
        con.execute("CREATE TABLE x.meta(k TEXT PRIMARY KEY, v TEXT)")
        con.execute("CREATE TABLE x.sounds(relpath TEXT PRIMARY KEY, %s)" % ",".join(PORTABLE))
        con.execute("CREATE TABLE x.wave(relpath TEXT PRIMARY KEY, data BLOB)")
        cols = ",".join(PORTABLE)
        con.execute(f"INSERT OR IGNORE INTO x.sounds(relpath,{cols}) "
                    f"SELECT replace(relpath,'\\','/'),{cols} FROM sounds WHERE library_id=?", (lib_id,))
        n = con.execute("SELECT COUNT(*) FROM x.sounds").fetchone()[0]
        nw = 0
        if with_waves and not cancelled():
            con.execute("INSERT OR IGNORE INTO x.wave SELECT replace(s.relpath,'\\','/'), w.data "
                        "FROM wave w JOIN sounds s ON s.id=w.id WHERE s.library_id=?", (lib_id,))
            nw = con.execute("SELECT COUNT(*) FROM x.wave").fetchone()[0]
        meta = {"version": INDEX_VERSION, "name": name, "count": n, "waves": nw,
                "exported": time.strftime("%d.%m.%Y %H:%M"), "source_path": root}
        con.executemany("INSERT INTO x.meta VALUES (?,?)", [(k, str(v)) for k, v in meta.items()])
        con.commit()
    finally:
        con.execute("DETACH DATABASE x")
    if cancelled():
        os.remove(tmp)
        return None
    os.replace(tmp, dest)
    return n, nw


def import_index(con, lib_id, src, root, progress=None, cancelled=lambda: False):
    """Importe un .sonolib dans la bibliothèque lib_id (dont le dossier est root sur ce PC)."""
    con.commit()
    con.execute("ATTACH DATABASE ? AS x", (src,))
    try:
        existing = {p: i for i, p in con.execute("SELECT id, path FROM sounds WHERE library_id=?", (lib_id,))}
        total = con.execute("SELECT COUNT(*) FROM x.sounds").fetchone()[0]
        cols = ",".join(PORTABLE)
        last, done = 0, 0
        while not cancelled():
            batch = con.execute(f"SELECT rowid, relpath, {cols} FROM x.sounds WHERE rowid>? ORDER BY rowid LIMIT 2000",
                                (last,)).fetchall()
            if not batch:
                break
            for row in batch:
                rel = row[1]
                meta = dict(zip(PORTABLE, row[2:]))
                meta["relpath"] = rel
                meta["path"] = os.path.join(root, *rel.split("/"))
                meta["folder"] = folder_words(rel)
                upsert_sound(con, lib_id, meta, existing.get(meta["path"]))
            last = batch[-1][0]
            done += len(batch)
            con.commit()
            if progress:
                progress(done, total)
        nw = 0
        if not cancelled():
            nw = con.execute("INSERT OR REPLACE INTO wave(id, data) SELECT s.id, w.data FROM x.wave w "
                             "JOIN sounds s ON s.library_id=? AND s.relpath=w.relpath", (lib_id,)).rowcount
            con.commit()
    finally:
        con.execute("DETACH DATABASE x")
    return done, nw


def wave_stats(con, lib_id):
    n = con.execute("SELECT COUNT(*) FROM sounds WHERE library_id=?", (lib_id,)).fetchone()[0]
    nw, size = con.execute("SELECT COUNT(*), IFNULL(SUM(length(w.data)),0) FROM wave w "
                           "JOIN sounds s ON s.id=w.id WHERE s.library_id=?", (lib_id,)).fetchone()
    return n, nw, size


# ---------------------------------------------------------------- search
_TOKEN = re.compile(r'(-?)"([^"]+)"|(-?)([^\s,;]+)')


def parse_terms(text):
    """'fly insect -wing "close up"' -> [('fly',False),('insect',False),('wing',True),('close up',False)]"""
    out = []
    for m in _TOKEN.finditer(text or ""):
        neg = bool(m.group(1) or m.group(3))
        term = (m.group(2) or m.group(4) or "").strip()
        if term and term != "-":
            out.append((term, neg))
    return out


def fts_query(terms):
    def q(t):
        words = re.findall(r"\w+", t, re.UNICODE)
        return '"%s"*' % " ".join(words) if words else None
    pos = [q(t) for t, n in terms if not n]
    neg = [q(t) for t, n in terms if n]
    pos, neg = [p for p in pos if p], [x for x in neg if x]
    if not pos:
        return None, neg
    s = " AND ".join(pos)
    for n in neg:
        s = f"({s}) NOT {n}"
    return s, []


SORT_SQL = {
    "name": "s.name COLLATE NOCASE", "description": "s.description COLLATE NOCASE",
    "category": "s.category COLLATE NOCASE, s.subcategory COLLATE NOCASE",
    "subcategory": "s.subcategory COLLATE NOCASE", "library": "l.name COLLATE NOCASE",
    "duration": "s.duration", "channels": "s.channels", "samplerate": "s.samplerate",
    "bits": "s.bits", "format": "s.format",
}

ROW_SQL = ("SELECT s.id,s.name,s.description,s.category,s.subcategory,l.name,s.duration,"
           "s.channels,s.samplerate,s.bits,s.format,s.path,s.keywords,s.filename,"
           "s.size,s.catid,s.source,s.relpath FROM sounds s JOIN libraries l ON l.id=s.library_id")


def search_ids(con, terms, library_id=None, category=None, subcategory=None,
               channels=None, sort="name", desc=False):
    """Renvoie la liste ordonnée des id correspondants (les lignes sont chargées à la demande)."""
    where, args = [], []
    match, orphan_neg = fts_query(terms)
    if match:
        where.append("s.id IN (SELECT rowid FROM sounds_fts WHERE sounds_fts MATCH ?)")
        args.append(match)
    for n in orphan_neg:  # uniquement des exclusions
        where.append("s.id NOT IN (SELECT rowid FROM sounds_fts WHERE sounds_fts MATCH ?)")
        args.append(n)
    if library_id:
        where.append("s.library_id=?"); args.append(library_id)
    for col, val in (("category", category), ("subcategory", subcategory)):
        if val is None:
            continue
        if val == "":
            where.append(f"(s.{col} IS NULL OR s.{col}='')")
        else:  # forme indexable
            where.append(f"s.{col}=?"); args.append(val)
    if channels == "mono":
        where.append("s.channels=1")
    elif channels == "stereo":
        where.append("s.channels=2")
    elif channels == "multi":
        where.append("s.channels>2")
    sql = "SELECT s.id FROM sounds s"
    order = SORT_SQL.get(sort, SORT_SQL["name"])
    if "l." in order:
        sql += " JOIN libraries l ON l.id=s.library_id"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if desc:
        order = ", ".join(p + " DESC" for p in order.split(", "))
    sql += f" ORDER BY {order}, s.id"
    try:
        return [r[0] for r in con.execute(sql, args)]
    except sqlite3.OperationalError:
        return []


def fetch_rows(con, ids):
    if not ids:
        return []
    return con.execute(ROW_SQL + " WHERE s.id IN (%s)" % ",".join("?" * len(ids)), list(ids)).fetchall()


def libraries(con):
    return con.execute(
        "SELECT l.id, l.name, l.path, COUNT(s.id) FROM libraries l "
        "LEFT JOIN sounds s ON s.library_id=l.id GROUP BY l.id ORDER BY l.name COLLATE NOCASE").fetchall()


def category_tree(con, library_id=None):
    sql = "SELECT IFNULL(category,''), IFNULL(subcategory,''), COUNT(*) FROM sounds"
    args = []
    if library_id:
        sql += " WHERE library_id=?"; args.append(library_id)
    sql += " GROUP BY 1,2 ORDER BY 1 COLLATE NOCASE, 2 COLLATE NOCASE"
    return con.execute(sql, args).fetchall()
