import hashlib
import json
import pickle
import zipfile
from datetime import datetime
from pathlib import Path
from einstellungen import pfad_programmdatei, ordner_programmdateien, BILDFORMATE

DB_DATEIEN = ("personen.pkl", "bilder.pkl", "einstellungen.pkl", "warteschlange.pkl")
BACKUP_ORDNER = "backups"


def _datei_hash(pfad):
    sha = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def _db_pfade():
    ordner = ordner_programmdateien()
    return {name: ordner / name for name in DB_DATEIEN}


def _backup_zip(ziel):
    pfade = _db_pfade()
    manifest = {
        "produkt": "NeuraPix",
        "erstellt": datetime.now().isoformat(timespec="seconds"),
        "dateien": {},
    }
    with zipfile.ZipFile(ziel, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, pfad in pfade.items():
            if pfad.is_file():
                z.write(pfad, arcname=name)
                manifest["dateien"][name] = _datei_hash(pfad)
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def erstelle_backup(grund="manuell", erzwingen=True):
    ordner = ordner_programmdateien()
    backup_ordner = ordner / BACKUP_ORDNER
    backup_ordner.mkdir(parents=True, exist_ok=True)
    jetzt = datetime.now()
    if grund == "automatisch" and not erzwingen:
        vorhanden = list(backup_ordner.glob(f"automatisch_{jetzt:%Y%m%d}_*.zip"))
        if vorhanden:
            return vorhanden[-1]
    ziel = backup_ordner / f"{grund}_{jetzt:%Y%m%d_%H%M%S}.zip"
    manifest = _backup_zip(ziel)
    if not manifest["dateien"]:
        ziel.unlink(missing_ok=True)
        return None
    # Automatische Sicherungen auf die letzten 30 begrenzen.
    if grund == "automatisch":
        backups = sorted(backup_ordner.glob("automatisch_*.zip"), key=lambda p: p.stat().st_mtime)
        for alt in backups[:-30]:
            alt.unlink(missing_ok=True)
    return ziel


def _pruefe_pickle_inhalt(name, daten):
    fehler = []
    if name == "personen.pkl":
        if not isinstance(daten, list):
            return ["Personendatenbank ist keine Liste."]
        for i, person in enumerate(daten):
            if not isinstance(person, dict):
                fehler.append(f"Person {i+1}: Datensatz ist kein Dictionary.")
                continue
            if not isinstance(person.get("name"), str) or not person["name"].strip():
                fehler.append(f"Person {i+1}: Name fehlt oder ist ungültig.")
            if not isinstance(person.get("bilder"), list):
                fehler.append(f"Person {i+1}: Bilderliste fehlt oder ist ungültig.")
            else:
                for j, bild in enumerate(person["bilder"]):
                    if not isinstance(bild, dict) or "hash" not in bild or "embedding" not in bild:
                        fehler.append(f"Person {i+1}, Bild {j+1}: Hash oder Gesichtsvektor fehlt.")
    elif name == "bilder.pkl":
        if not isinstance(daten, dict):
            return ["Bildverwaltung ist kein Dictionary."]
        for key in ("verarbeitet", "verworfen"):
            if not isinstance(daten.get(key, []), list):
                fehler.append(f"Bildverwaltung: '{key}' ist keine Liste.")
    elif name == "einstellungen.pkl" and not isinstance(daten, dict):
        fehler.append("Einstellungsdatei ist kein Dictionary.")
    return fehler


def pruefe_datenbank():
    pfade = _db_pfade()
    bericht = {
        "dateien": [],
        "fehler": [],
        "warnungen": [],
        "personen": 0,
        "gesichter": 0,
        "fehlende_bilder": 0,
        "doppelte_hashes": [],
    }
    geladene = {}
    for name, pfad in pfade.items():
        if not pfad.exists():
            if name in ("personen.pkl", "bilder.pkl"):
                bericht["warnungen"].append(f"{name}: Datei existiert noch nicht.")
            continue
        try:
            with open(pfad, "rb") as f:
                daten = pickle.load(f)
            geladene[name] = daten
            fehler = _pruefe_pickle_inhalt(name, daten)
            bericht["fehler"].extend(f"{name}: {x}" for x in fehler)
            bericht["dateien"].append(f"{name}: lesbar ({pfad.stat().st_size:,} Bytes)")
        except Exception as exc:
            bericht["fehler"].append(f"{name}: kann nicht gelesen werden ({exc})")

    personen = geladene.get("personen.pkl", [])
    if isinstance(personen, list):
        bericht["personen"] = len(personen)
        hash_map = {}
        for person in personen:
            if not isinstance(person, dict):
                continue
            for bild in person.get("bilder", []) if isinstance(person.get("bilder"), list) else []:
                if not isinstance(bild, dict):
                    continue
                bericht["gesichter"] += 1
                hashwert = bild.get("hash")
                if hashwert:
                    hash_map.setdefault(hashwert, []).append(person.get("name", "Unbekannt"))
                datei = Path(str(bild.get("datei", ""))).expanduser()
                if not datei.is_file():
                    bericht["fehlende_bilder"] += 1
        bericht["doppelte_hashes"] = [
            {"hash": h, "personen": namen}
            for h, namen in hash_map.items() if len(namen) > 1
        ]
        if bericht["fehlende_bilder"]:
            bericht["warnungen"].append(
                f"{bericht['fehlende_bilder']} gespeicherte Bildpfade sind aktuell nicht erreichbar."
            )
        if bericht["doppelte_hashes"]:
            bericht["warnungen"].append(
                f"{len(bericht['doppelte_hashes'])} Hashwerte kommen mehrfach in Personendatensätzen vor."
            )

    return bericht


def finde_dateiduplikate(ordner, fortschritt=None):
    """
    Findet bytegenau identische Bilddateien über SHA-256.

    fortschritt(event) erhält Status-Dictionaries:
      start:     Anzahl Dateien und Gesamtbytes
      progress:  verarbeitete Dateien/Bytes und Zeitmessung
      complete:  Abschlussdaten

    Die Zeitreferenz wird aus den ersten zwei gehashten Dateien gebildet.
    Die Restzeitschätzung basiert auf der gemessenen Bytes-pro-Sekunde-Rate.
    """
    import time

    def melden(typ, **daten):
        if fortschritt is not None:
            try:
                fortschritt({"typ": typ, **daten})
            except Exception:
                # Ein Anzeige-Callback darf die eigentliche Suche nicht abbrechen.
                pass

    ordner = Path(ordner).expanduser().resolve()
    endungen = {e.casefold() for gruppe in BILDFORMATE.values() for e in gruppe}

    dateien = []
    fehler = []
    gesamt_bytes = 0

    for pfad in ordner.rglob("*"):
        if not pfad.is_file() or pfad.suffix.casefold() not in endungen:
            continue
        dateien.append(pfad)
        try:
            gesamt_bytes += pfad.stat().st_size
        except OSError as exc:
            fehler.append(f"{pfad}: {exc}")

    anzahl_dateien = len(dateien)
    melden(
        "start",
        anzahl=anzahl_dateien,
        gesamt_bytes=gesamt_bytes,
    )

    hash_map = {}
    verarbeitet = 0
    bytes_verarbeitet = 0
    startzeit = time.perf_counter()
    referenz_rate = None

    for pfad in dateien:
        try:
            groesse = pfad.stat().st_size
            hash_start = time.perf_counter()
            h = _datei_hash(pfad)
            hash_dauer = time.perf_counter() - hash_start
            hash_map.setdefault(h, []).append(str(pfad))
            bytes_verarbeitet += groesse
            verarbeitet += 1

            # Nach den ersten zwei Dateien steht eine erste Messreferenz bereit.
            if verarbeitet == 2 and hash_dauer >= 0:
                erste_zwei_bytes = sum(
                    Path(p).stat().st_size
                    for dateien_mit_hash in hash_map.values()
                    for p in dateien_mit_hash
                )
                erste_zwei_dauer = time.perf_counter() - startzeit
                if erste_zwei_dauer > 0 and erste_zwei_bytes > 0:
                    referenz_rate = erste_zwei_bytes / erste_zwei_dauer

            # Dynamisch aktualisierte Rate glättet die anfängliche Stichprobe.
            vergangen = time.perf_counter() - startzeit
            aktuelle_rate = (
                bytes_verarbeitet / vergangen if vergangen > 0 and bytes_verarbeitet > 0
                else referenz_rate
            )
            rest_bytes = max(0, gesamt_bytes - bytes_verarbeitet)
            rest_sekunden = (
                rest_bytes / aktuelle_rate
                if aktuelle_rate and aktuelle_rate > 0
                else None
            )

            melden(
                "progress",
                verarbeitet=verarbeitet,
                anzahl=anzahl_dateien,
                bytes_verarbeitet=bytes_verarbeitet,
                gesamt_bytes=gesamt_bytes,
                vergangen=vergangen,
                rest_sekunden=rest_sekunden,
                referenz_rate=referenz_rate,
            )
        except OSError as exc:
            fehler.append(f"{pfad}: {exc}")
            verarbeitet += 1
            melden(
                "progress",
                verarbeitet=verarbeitet,
                anzahl=anzahl_dateien,
                bytes_verarbeitet=bytes_verarbeitet,
                gesamt_bytes=gesamt_bytes,
                vergangen=time.perf_counter() - startzeit,
                rest_sekunden=None,
                referenz_rate=referenz_rate,
            )

    gruppen = [
        {"hash": h, "dateien": dateiliste}
        for h, dateiliste in hash_map.items() if len(dateiliste) > 1
    ]
    dauer = time.perf_counter() - startzeit
    melden(
        "complete",
        verarbeitet=verarbeitet,
        anzahl=anzahl_dateien,
        dauer=dauer,
        gruppen=len(gruppen),
        fehler=len(fehler),
    )
    return gruppen, fehler, sum(len(x) for x in hash_map.values())


def exportiere_datenbank(ziel):
    ziel = Path(ziel)
    manifest = _backup_zip(ziel)
    if not manifest["dateien"]:
        ziel.unlink(missing_ok=True)
        raise RuntimeError("Es sind noch keine Datenbankdateien zum Exportieren vorhanden.")
    return ziel


def _validiere_archiv(quelle):
    with zipfile.ZipFile(quelle, "r") as z:
        namen = set(z.namelist())
        erlaubte = set(DB_DATEIEN) | {"manifest.json"}
        if not namen.issubset(erlaubte) or not (namen & set(DB_DATEIEN)):
            raise ValueError("Das Archiv enthält keine gültige NeuraPix-Datenbank.")
        manifest = json.loads(z.read("manifest.json")) if "manifest.json" in namen else None
        daten = {}
        for name in DB_DATEIEN:
            if name not in namen:
                continue
            raw = z.read(name)
            if manifest and manifest.get("dateien", {}).get(name):
                if hashlib.sha256(raw).hexdigest() != manifest["dateien"][name]:
                    raise ValueError(f"Prüfsummenfehler in {name}.")
            obj = pickle.loads(raw)
            fehler = _pruefe_pickle_inhalt(name, obj)
            if fehler:
                raise ValueError(f"{name}: " + "; ".join(fehler))
            daten[name] = raw
    return daten


def stelle_datenbank_wieder_her(quelle):
    daten = _validiere_archiv(quelle)
    backup = erstelle_backup("vor_wiederherstellung")
    ordner = ordner_programmdateien()
    temporaer = []
    try:
        for name, raw in daten.items():
            temp = ordner / f".{name}.restore.tmp"
            temp.write_bytes(raw)
            temporaer.append((temp, ordner / name))
        for temp, ziel in temporaer:
            temp.replace(ziel)
    finally:
        for temp, _ in temporaer:
            temp.unlink(missing_ok=True)
    return backup, list(daten)
