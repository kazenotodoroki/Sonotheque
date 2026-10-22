"""Tâches de fond : scan incrémental, import/export d'index, calcul des formes d'onde."""
import os
import traceback
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal

from . import db, metadata

SKIP_DIRS = {"$recycle.bin", "system volume information", "__macosx"}


class Job(QObject):
    progress = Signal(int, int, str)   # fait, total (0 = indéterminé), libellé
    changed = Signal()                 # des lignes ont été enregistrées
    finished = Signal(object)          # résultat (ou exception)

    def __init__(self, db_path):
        super().__init__()
        self.db_path, self.cancelled = db_path, False

    def run(self):
        res = None
        try:
            res = self.work()
        except Exception as e:
            traceback.print_exc()
            res = e
        self.finished.emit(res)

    def work(self):
        raise NotImplementedError


def walk_audio(root):
    """Parcourt le dossier ; sous Windows, os.scandir fournit taille/date sans appel système en plus."""
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                n = e.name
                if n.startswith(".") or n.startswith("._"):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        if n.lower() not in SKIP_DIRS:
                            stack.append(e.path)
                    elif os.path.splitext(n)[1].lower() in metadata.AUDIO_EXT:
                        st = e.stat()
                        yield e.path, st.st_size, st.st_mtime
                except OSError:
                    pass


def same_file(old_size, old_mtime, size, mtime):
    """Tolère FAT/exFAT (2 s) et les décalages de fuseau/heure d'été lors d'une copie."""
    if old_size != size:
        return False
    d = abs((old_mtime or 0) - mtime)
    return d <= 2.01 or (d < 26 * 3600 and abs(d - round(d / 3600) * 3600) <= 2.01)


class ScanJob(Job):
    def __init__(self, db_path, lib_ids=None):
        super().__init__(db_path)
        self.lib_ids = lib_ids

    def work(self):
        con = db.connect(self.db_path)
        libs = con.execute("SELECT id,name,path FROM libraries").fetchall()
        if self.lib_ids:
            libs = [l for l in libs if l[0] in self.lib_ids]
        read = 0
        for lib_id, name, root in libs:
            if self.cancelled:
                break
            if not os.path.isdir(root):   # disque débranché : on ne supprime rien
                continue
            self.progress.emit(0, 0, f"Vérification de {name}…")
            files = list(walk_audio(root))
            if self.cancelled:
                break
            existing = {p: (i, s, m) for i, p, s, m in con.execute(
                "SELECT id,path,size,mtime FROM sounds WHERE library_id=?", (lib_id,))}
            total, dirty, touch = len(files), 0, []
            for n, (p, size, mtime) in enumerate(files, 1):
                if self.cancelled:
                    break
                ex = existing.pop(p, None)
                if ex and same_file(ex[1], ex[2], size, mtime):
                    if ex[2] != mtime:
                        touch.append((mtime, ex[0]))
                    continue
                try:
                    meta = metadata.read_file(p, root)
                    db.upsert_sound(con, lib_id, meta, ex[0] if ex else None)
                    dirty += 1
                    read += 1
                except Exception:
                    traceback.print_exc()
                if n % 250 == 0:
                    if dirty:
                        con.commit(); dirty = 0
                        self.changed.emit()
                    self.progress.emit(n, total, name)
            if touch:
                con.executemany("UPDATE sounds SET mtime=? WHERE id=?", touch)
            if not self.cancelled and existing:
                db.delete_sounds(con, [v[0] for v in existing.values()])
            con.commit()
            self.progress.emit(total, total, name)
            self.changed.emit()
        con.close()
        return read


class ImportJob(Job):
    def __init__(self, db_path, lib_id, src, root, name):
        super().__init__(db_path)
        self.lib_id, self.src, self.root, self.name = lib_id, src, root, name

    def work(self):
        con = db.connect(self.db_path)
        self.progress.emit(0, 0, f"Import de l'index de {self.name}…")

        def cb(done, total):
            self.progress.emit(done, total, f"Import · {self.name}")
            if done % 20000 < 2000:
                self.changed.emit()
        res = db.import_index(con, self.lib_id, self.src, self.root, cb, lambda: self.cancelled)
        con.close()
        self.changed.emit()
        return res


class ExportJob(Job):
    def __init__(self, db_path, lib_id, dest, with_waves, name):
        super().__init__(db_path)
        self.lib_id, self.dest, self.with_waves, self.name = lib_id, dest, with_waves, name

    def work(self):
        con = db.connect(self.db_path)
        self.progress.emit(0, 0, f"Export de l'index de {self.name}…")
        res = db.export_index(con, self.lib_id, self.dest, self.with_waves, lambda: self.cancelled)
        con.close()
        return res


# ---------------------------------------------------------------- formes d'onde
BINS = 600


def compute_peaks(path, duration_hint=None):
    import soundfile as sf
    with sf.SoundFile(path) as f:
        n = f.frames if f.frames and f.frames > 0 else int((duration_hint or 1) * f.samplerate)
        n = max(n, 1)
        peaks = np.zeros(BINS, np.float32)
        pos = 0
        for block in f.blocks(blocksize=1 << 17, dtype="float32", always_2d=True):
            a = np.abs(block).max(axis=1)
            idx = np.minimum((np.arange(pos, pos + len(a), dtype=np.int64) * BINS) // n, BINS - 1)
            starts = np.flatnonzero(np.r_[True, idx[1:] != idx[:-1]])
            vals = np.maximum.reduceat(a, starts)
            b = idx[starts]
            peaks[b] = np.maximum(peaks[b], vals)
            pos += len(a)
    return np.clip(peaks, 0, 1)


def _safe_peaks(item):
    sid, path, dur = item
    try:
        return sid, db.encode_wave(compute_peaks(path, dur))
    except Exception:
        return sid, None


class WavesJob(Job):
    """Calcule en lot toutes les formes d'onde manquantes (reprend là où il s'est arrêté)."""

    def __init__(self, db_path, lib_ids):
        super().__init__(db_path)
        self.lib_ids = lib_ids

    def work(self):
        con = db.connect(self.db_path)
        q = ",".join("?" * len(self.lib_ids))
        todo = con.execute(f"SELECT s.id, s.path, s.duration FROM sounds s LEFT JOIN wave w ON w.id=s.id "
                           f"WHERE w.id IS NULL AND s.library_id IN ({q}) ORDER BY s.path", self.lib_ids).fetchall()
        total, done = len(todo), 0
        workers = max(2, min(8, (os.cpu_count() or 4)))
        with ThreadPoolExecutor(workers) as ex:
            for i in range(0, total, 256):
                if self.cancelled:
                    break
                rows = [r for r in ex.map(_safe_peaks, todo[i:i + 256]) if r[1] is not None]
                con.executemany("INSERT OR REPLACE INTO wave(id, data) VALUES (?,?)", rows)
                con.commit()
                done = min(i + 256, total)
                self.progress.emit(done, total, "Formes d'onde")
        con.close()
        return done


class PeakSignals(QObject):
    done = Signal(int, object)


class PeakJob(QRunnable):
    """Forme d'onde du son sélectionné : cache, sinon calcul immédiat."""

    def __init__(self, db_path, sound_id, path, duration, signals):
        super().__init__()
        self.db_path, self.sid, self.path, self.dur, self.s = db_path, sound_id, path, duration, signals

    def run(self):
        peaks = None
        try:
            con = db.connect(self.db_path)
            row = con.execute("SELECT data FROM wave WHERE id=?", (self.sid,)).fetchone()
            if row:
                peaks = db.decode_wave(row[0])
            else:
                peaks = compute_peaks(self.path, self.dur)
                blob = db.encode_wave(peaks)
                con.execute("INSERT OR REPLACE INTO wave(id,data) VALUES (?,?)", (self.sid, blob))
                con.commit()
                peaks = db.decode_wave(blob)
            con.close()
        except Exception:
            traceback.print_exc()
        self.s.done.emit(self.sid, peaks)
