import os
import pickle
import shutil
from pathlib import Path

APP_NAME = "neurapix"
DATEN_BASIS = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
START_DATEI = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME / "einstellungen.pkl"
ALTE_START_DATEI = Path(__file__).resolve().with_name("einstellungen.pkl")
ALTE_HOME_DATEI = Path.home() / "einstellungen.pkl"

BILDFORMATE = {
    "JPG": (".jpg",), "JPEG": (".jpeg",), "PNG": (".png",), "WEBP": (".webp",),
    "BMP": (".bmp",), "TIFF / TIF": (".tif", ".tiff"), "HEIC": (".heic",), "HEIF": (".heif",),
}
STANDARD = {
    "COUNTDOWN_SEKUNDEN": 5, "DATEN_ORDNER": str(DATEN_BASIS),
    "ANALYSE_ORDNER": [], "MIN_GESICHTSGROESSE_PROZENT": 0,
    "STATUSLEISTE_AKTIV": True, "KARUSSELL_AKTIV": True,
    "SCHLIESSEN_IN_TRAY": True, "MOUSEOVER_AKTIV": True,
    "MOUSEOVER_VERZOEGERUNG_MS": 100,
    "BILDFORMATE": {"JPG": True, "JPEG": True, "PNG": True, "WEBP": True,
                    "BMP": False, "TIFF / TIF": False, "HEIC": False, "HEIF": False},
}

def aktive_endungen():
    auswahl = EINSTELLUNGEN.get("BILDFORMATE", {})
    return {e for n, es in BILDFORMATE.items() if auswahl.get(n, n in ("JPG", "JPEG")) for e in es}

def _lade_pickle(pfad):
    try:
        with open(pfad, "rb") as f:
            daten = pickle.load(f)
        return daten if isinstance(daten, dict) else None
    except (OSError, pickle.PickleError, EOFError, AttributeError, ValueError, TypeError):
        return None

def _migriere_altdaten(ziel):
    ziel.mkdir(parents=True, exist_ok=True)
    kandidaten = [
        Path.home(), Path(__file__).resolve().parent,
        Path.home() / "fotoscan" / "Programmdateien",
    ]
    for quelle in kandidaten:
        if not quelle.is_dir():
            continue
        for name in ("personen.pkl", "bilder.pkl", "warteschlange.pkl", "einstellungen.pkl"):
            src, dst = quelle / name, ziel / name
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)
        src, dst = quelle / ".thumbnails", ziel / ".thumbnails"
        if src.is_dir() and not dst.exists():
            shutil.copytree(src, dst, dirs_exist_ok=True)

def lade_einstellungen():
    daten = _lade_pickle(START_DATEI)
    if daten is None:
        daten = _lade_pickle(ALTE_START_DATEI) or _lade_pickle(ALTE_HOME_DATEI)
    if daten is None:
        daten = STANDARD.copy()
    for k, v in STANDARD.items():
        daten.setdefault(k, v.copy() if isinstance(v, dict) else v)
    # Den vom Benutzer gewählten Datenordner beibehalten.
    daten_pfad = Path(daten.get("DATEN_ORDNER", str(DATEN_BASIS))).expanduser()
    if not daten_pfad.is_absolute():
        daten_pfad = DATEN_BASIS
    daten_pfad.mkdir(parents=True, exist_ok=True)

    # Datenmigration genau einmal durchführen. Der Marker liegt unabhängig
    # vom gewählten Datenordner im festen NeuraPix-Anwendungsdatenverzeichnis.
    migrations_marker = DATEN_BASIS / ".migration_v1_completed"
    if not migrations_marker.exists():
        if not (daten_pfad / "personen.pkl").exists() and not (daten_pfad / "bilder.pkl").exists():
            _migriere_altdaten(daten_pfad)

        try:
            migrations_marker.write_text("Migration abgeschlossen.\\n", encoding="utf-8")
        except OSError:
            pass
    daten["DATEN_ORDNER"] = str(daten_pfad)
    ordner = daten.get("ANALYSE_ORDNER", [])
    if not isinstance(ordner, (list, tuple)): ordner = []
    daten["ANALYSE_ORDNER"] = list(dict.fromkeys(str(Path(p).expanduser()) for p in ordner if isinstance(p, (str, Path)) and str(p).strip()))
    try:
        daten["MIN_GESICHTSGROESSE_PROZENT"] = max(
            0.0, min(100.0, float(daten.get("MIN_GESICHTSGROESSE_PROZENT", 0)))
        )
    except (TypeError, ValueError):
        daten["MIN_GESICHTSGROESSE_PROZENT"] = 0.0
    for k in ("STATUSLEISTE_AKTIV", "KARUSSELL_AKTIV", "SCHLIESSEN_IN_TRAY", "MOUSEOVER_AKTIV"):
        daten[k] = bool(daten.get(k, STANDARD[k]))
    try: daten["MOUSEOVER_VERZOEGERUNG_MS"] = max(0, int(daten.get("MOUSEOVER_VERZOEGERUNG_MS", 100)))
    except (TypeError, ValueError): daten["MOUSEOVER_VERZOEGERUNG_MS"] = 100
    formate = daten.get("BILDFORMATE", {})
    daten["BILDFORMATE"] = {n: bool(formate.get(n, STANDARD["BILDFORMATE"][n])) for n in BILDFORMATE}
    return daten

def ordner_programmdateien():
    p = Path(EINSTELLUNGEN["DATEN_ORDNER"]).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p

def pfad_programmdatei(dateiname):
    return ordner_programmdateien() / dateiname

def speichere_einstellungen(daten):
    START_DATEI.parent.mkdir(parents=True, exist_ok=True)
    with open(START_DATEI, "wb") as f: pickle.dump(daten, f)
    ziel = Path(daten["DATEN_ORDNER"]).expanduser()
    ziel.mkdir(parents=True, exist_ok=True)
    with open(ziel / "einstellungen.pkl", "wb") as f: pickle.dump(daten, f)

EINSTELLUNGEN = lade_einstellungen()
COUNTDOWN_SEKUNDEN = EINSTELLUNGEN["COUNTDOWN_SEKUNDEN"]
