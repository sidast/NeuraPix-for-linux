import cv2
import hashlib
import pickle
import os
import tempfile
from types import SimpleNamespace
import numpy as np
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from einstellungen import EINSTELLUNGEN, pfad_programmdatei
from pathlib import Path

def ermittle_embedding(datei, app):
    bild = cv2.imread(str(datei))

    if bild is None:
        print("Bild konnte nicht geladen werden.")
        return None

    gesichter = app.get(bild)

    if len(gesichter) == 0:
        print("Kein Gesicht gefunden.")
        return None

    return gesichter

def berechne_hash(datei):
    sha = hashlib.sha256()

    with open(datei, "rb") as f:
        while True:
            block = f.read(8192)
            if not block:
                break
            sha.update(block)

    return sha.hexdigest()

def _pickle_sicher_speichern(dateiname, daten):
    ziel = pfad_programmdatei(dateiname)
    fd, temp_name = tempfile.mkstemp(prefix=f".{dateiname}.", suffix=".tmp", dir=ziel.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(daten, f, protocol=pickle.HIGHEST_PROTOCOL)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, ziel)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

def speichere_personen(personen):
    _pickle_sicher_speichern("personen.pkl", personen)

def speichere_bilder(bilder):
    _pickle_sicher_speichern("bilder.pkl", bilder)

def lade_personen():
    try:
        with open(pfad_programmdatei("personen.pkl"), "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        return []

def lade_bilder():
    try:
        with open(pfad_programmdatei("bilder.pkl"), "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        return {
            "verarbeitet": [],
            "verworfen": []
        }

def hash_existiert(personen, hashwert):
    for person in personen:
        for bild in person["bilder"]:
            if bild["hash"] == hashwert:
                return True

    return False

def lade_warteschlange():
    try:
        with open(pfad_programmdatei("warteschlange.pkl"), "rb") as f:
            daten = pickle.load(f)
        return daten if isinstance(daten, list) else []
    except (FileNotFoundError, EOFError, pickle.PickleError, OSError):
        return []


def speichere_warteschlange(warteschlange):
    _pickle_sicher_speichern("warteschlange.pkl", warteschlange)


def warteschlange_anzahl():
    return len(lade_warteschlange())


def warteschlange_mit_personen_abgleichen(personen=None, schwellwert=None):
    """Ordnet offene Queue-Vektoren nach einer neuen manuellen Zuordnung automatisch zu."""
    warteschlange = lade_warteschlange()
    if not warteschlange:
        return 0

    if personen is None:
        personen = lade_personen()
    if schwellwert is None:
        schwellwert = float(EINSTELLUNGEN.get("ERKENNUNGSSCHWELLE", 1.2))
    else:
        schwellwert = float(schwellwert)

    uebrig = []
    zugeordnet = 0
    erledigte_hashes = []

    for eintrag in warteschlange:
        try:
            embedding = np.asarray(eintrag["embedding"], dtype=np.float32)
            hashwert = eintrag["hash"]
        except (KeyError, TypeError, ValueError):
            uebrig.append(eintrag)
            continue

        beste_person = None
        kleinster_abstand = float("inf")
        for person in personen:
            for vorhandenes in person.get("bilder", []):
                try:
                    abstand = float(np.linalg.norm(
                        embedding - np.asarray(vorhandenes["embedding"], dtype=np.float32)
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
                if abstand < kleinster_abstand:
                    kleinster_abstand = abstand
                    beste_person = person

        if beste_person is None or kleinster_abstand >= schwellwert:
            uebrig.append(eintrag)
            continue

        # Identischen Datensatz nicht doppelt speichern, aber aus der Queue entfernen.
        bereits_vorhanden = any(
            bild.get("hash") == hashwert
            and np.linalg.norm(
                embedding - np.asarray(bild["embedding"], dtype=np.float32)
            ) < 1e-6
            for bild in beste_person.get("bilder", [])
            if "embedding" in bild
        )
        if not bereits_vorhanden:
            person_erweitern(
                beste_person,
                eintrag.get("datei", ""),
                hashwert,
                embedding,
            )

        zugeordnet += 1
        erledigte_hashes.append(hashwert)
        print(
            f"{Path(eintrag.get('datei', '')).name}: Warteschlangenvektor "
            f"automatisch {beste_person['name']} zugeordnet "
            f"(Abstand: {kleinster_abstand:.3f})."
        )

    if zugeordnet:
        speichere_personen(personen)
        speichere_warteschlange(uebrig)
        bildverwaltung = lade_bilder()
        status_map = bildverwaltung.setdefault("gesichter_status", {})
        noch_offen = {e.get("hash") for e in uebrig}
        for hashwert in erledigte_hashes:
            status = status_map.get(hashwert)
            if not isinstance(status, dict):
                continue
            status["abgeschlossen"] = int(status.get("abgeschlossen", 0)) + 1
            if (
                status.get("gesamt") is not None
                and status["abgeschlossen"] >= int(status["gesamt"])
                and hashwert not in noch_offen
            ):
                if hashwert not in bildverwaltung.setdefault("verarbeitet", []):
                    bildverwaltung["verarbeitet"].append(hashwert)
        speichere_bilder(bildverwaltung)

    return zugeordnet


def neue_person_anlegen(datei, gesicht, embedding, hashwert, personen, naechste_person, hauptfenster, namens_frame, STOP=None, vorausgefuellter_name=None, einzelbild=False, in_warteschlange=False):
    # Warteschlangeneinträge laden den Bildpfad als String aus der Datenbank.
    # Im restlichen Ablauf wird Path verwendet (z. B. datei.stem).
    datei = Path(datei)
    if in_warteschlange and not einzelbild:
        warteschlange = lade_warteschlange()
        bbox = [float(x) for x in gesicht.bbox.tolist()]
        warteschlange.append({
            "datei": str(datei),
            "bbox": bbox,
            "embedding": np.asarray(embedding, dtype=np.float32),
            "hash": hashwert,
        })
        speichere_warteschlange(warteschlange)
        print(f"Unbekanntes Gesicht für spätere Zuordnung vorgemerkt: {datei}")
        return naechste_person, "QUEUED"

    # Separates, kompaktes Fenster mit dem Originalbild und markiertem Gesicht.
    bild = cv2.imread(str(datei))

    dialog = tk.Toplevel(hauptfenster)
    dialog.title("Person zuordnen" if einzelbild else "Neue Person erkannt")
    dialog.transient(hauptfenster)
    dialog.resizable(False, False)

    rahmen = tk.Frame(dialog, padx=16, pady=12)
    rahmen.pack(fill="both", expand=True)

    ueberschrift = "Person zuordnen" if einzelbild else "Neue Person erkannt"
    tk.Label(rahmen, text=ueberschrift, font=("Arial", 13, "bold")).pack(
        pady=(0, 8)
    )

    bild_container = tk.Frame(rahmen, width=470, height=300)
    bild_container.pack(fill="both", expand=False)
    bild_container.pack_propagate(False)

    bild_tk = None
    if bild is not None:
        x1, y1, x2, y2 = gesicht.bbox.astype(int)
        cv2.rectangle(bild, (x1, y1), (x2, y2), (0, 255, 0), 3)
        bild_rgb = cv2.cvtColor(bild, cv2.COLOR_BGR2RGB)
        vorschau = Image.fromarray(bild_rgb)
        vorschau.thumbnail((460, 290), Image.Resampling.LANCZOS)
        bild_tk = ImageTk.PhotoImage(vorschau)
        bild_label = tk.Label(bild_container, image=bild_tk)
        bild_label.image = bild_tk
        bild_label.place(relx=0.5, rely=0.5, anchor="center")
    else:
        tk.Label(bild_container, text="Bild konnte nicht geladen werden.").place(
            relx=0.5, rely=0.5, anchor="center"
        )

    tk.Label(rahmen, text="Namen eingeben oder auswählen:", anchor="w").pack(
        fill="x", pady=(8, 4)
    )

    namen = [person["name"] for person in personen]
    eingabe = ttk.Combobox(rahmen, values=namen, font=("Arial", 13))
    eingabe.pack(fill="x")
    if vorausgefuellter_name:
        eingabe.set(vorausgefuellter_name)

    countdown = EINSTELLUNGEN["COUNTDOWN_SEKUNDEN"]
    countdown_label = tk.Label(
        rahmen, text=f"Automatischer Skip in {countdown}...", anchor="w"
    )
    countdown_label.pack(fill="x", pady=(6, 0))

    status_var = tk.StringVar(master=hauptfenster, value="WAIT")
    name_value = {"value": ""}

    def status_setzen(status):
        if status_var.get() != "WAIT":
            return
        name_value["value"] = eingabe.get().strip()
        status_var.set(status)
        try:
            if dialog.winfo_exists():
                dialog.destroy()
        except tk.TclError:
            pass

    def bestaetigen():
        status_setzen("OK")

    def skip():
        status_setzen("SKIP")

    def skip_rest():
        status_setzen("SKIP_REST")

    def bild_verwerfen():
        status_setzen("VERWERFEN")

    def stop():
        if STOP is not None:
            STOP["abbrechen"] = True
        status_setzen("STOP")

    dialog.protocol("WM_DELETE_WINDOW", skip)

    button_frame = tk.Frame(rahmen)
    button_frame.pack(fill="x", pady=(10, 0))
    for text, callback in (
        ("OK", bestaetigen),
        ("Skip", skip),
        ("Skip Rest", skip_rest),
        ("Ignorieren", bild_verwerfen),
        ("Stop", stop),
    ):
        tk.Button(button_frame, text=text, command=callback).pack(
            side="left", expand=True, fill="x", padx=2
        )

    def countdown_reset(event=None):
        nonlocal countdown
        if status_var.get() == "WAIT":
            countdown = EINSTELLUNGEN["COUNTDOWN_SEKUNDEN"]
            countdown_label.config(text=f"Automatischer Skip in {countdown}...")

    after_ids = {"stop": None, "countdown": None}

    def stop_pruefen():
        after_ids["stop"] = None
        if status_var.get() != "WAIT":
            return
        if STOP is not None and STOP.get("abbrechen"):
            status_setzen("STOP")
            return
        after_ids["stop"] = dialog.after(100, stop_pruefen)

    def countdown_tick():
        nonlocal countdown
        after_ids["countdown"] = None
        if status_var.get() != "WAIT":
            return
        if STOP is not None and STOP.get("abbrechen"):
            status_setzen("STOP")
            return
        countdown -= 1
        countdown_label.config(text=f"Automatischer Skip in {countdown}...")
        if countdown <= 0:
            skip()
        else:
            after_ids["countdown"] = dialog.after(1000, countdown_tick)

    eingabe.bind("<KeyRelease>", countdown_reset)
    eingabe.bind("<FocusIn>", countdown_reset)
    eingabe.bind("<<ComboboxSelected>>", countdown_reset)
    eingabe.bind("<Button-1>", countdown_reset)
    eingabe.bind("<Return>", lambda event: bestaetigen())
    dialog.bind("<Escape>", lambda event: stop())

    hauptfenster.update_idletasks()
    dialog.update_idletasks()
    breite = dialog.winfo_reqwidth()
    hoehe = dialog.winfo_reqheight()
    x = max(0, (dialog.winfo_screenwidth() - breite) // 2)
    y = max(0, (dialog.winfo_screenheight() - hoehe) // 2)
    dialog.geometry(f"+{x}+{y}")

    eingabe.focus_set()
    dialog.grab_set()
    after_ids["countdown"] = dialog.after(1000, countdown_tick)
    after_ids["stop"] = dialog.after(100, stop_pruefen)

    try:
        hauptfenster.wait_variable(status_var)
    finally:
        for after_id in after_ids.values():
            if after_id is not None:
                try:
                    dialog.after_cancel(after_id)
                except tk.TclError:
                    pass
        try:
            if dialog.winfo_exists():
                dialog.grab_release()
                dialog.destroy()
        except tk.TclError:
            pass

    name = name_value["value"]
    status = status_var.get()

    if status == "SKIP":
        return naechste_person, "SKIP"
    if status == "SKIP_REST":
        return naechste_person, "SKIP_REST"
    if status == "VERWERFEN":
        return naechste_person, "VERWERFEN"
    if status == "STOP":
        return naechste_person, "STOP"
    if status != "OK" or not name:
        return naechste_person, "SKIP"

    for person in personen:
        if person["name"].casefold() == name.casefold():
            person["bilder"].append({
                "datei": str(datei),
                "hash": hashwert,
                "embedding": embedding
            })
            print(f"{datei.stem} wurde der bestehenden Person {person['name']} hinzugefügt.")
            return naechste_person, "OK"

    personen.append({
        "label": f"Person_{naechste_person:03d}",
        "name": name,
        "bilder": [{
            "datei": str(datei),
            "hash": hashwert,
            "embedding": embedding
        }]
    })
    print(f"{datei.stem} wurde als neue Person {name} angelegt.")
    return naechste_person + 1, "OK"


def warteschlange_bearbeiten(hauptfenster, namens_frame, STOP=None):
    """Ordnet gespeicherte Gesichtsvektoren der Warteschlange Personen zu."""
    warteschlange = lade_warteschlange()
    if not warteschlange:
        return 0, 0

    personen = lade_personen()
    naechste_person = max(
        [int(p.get("label", "Person_000").split("_")[-1]) for p in personen
         if str(p.get("label", "")).startswith("Person_")] or [0]
    ) + 1
    schwellwert = float(EINSTELLUNGEN.get("ERKENNUNGSSCHWELLE", 1.2))
    erledigt = 0
    uebrig = list(warteschlange)

    for eintrag in list(warteschlange):
        if STOP is not None and STOP.get("abbrechen"):
            break

        datei = Path(eintrag.get("datei", ""))
        if not datei.is_file():
            # Fehlende Dateien bleiben in der Warteschlange, bis sie wieder
            # verfügbar sind oder der Benutzer sie anderweitig bereinigt.
            continue

        embedding = np.asarray(eintrag["embedding"], dtype=np.float32)
        beste_person, abstand = finde_beste_person(embedding, personen, 0.5)

        if beste_person is not None and abstand < schwellwert:
            person_erweitern(
                beste_person, datei, eintrag["hash"], embedding
            )
            status = "OK"
            print(
                f"{datei.name}: gespeicherter Vektor automatisch "
                f"{beste_person['name']} zugeordnet (Abstand: {abstand:.3f})."
            )
        else:
            gesicht = SimpleNamespace(
                bbox=np.asarray(eintrag["bbox"], dtype=np.float32)
            )
            naechste_person, status = neue_person_anlegen(
                datei, gesicht, embedding, eintrag["hash"], personen,
                naechste_person, hauptfenster, namens_frame,
                STOP=STOP, einzelbild=True,
            )

        if status in ("OK", "VERWERFEN"):
            index = next(
                (i for i, kandidat in enumerate(uebrig) if kandidat is eintrag),
                None,
            )
            if index is not None:
                uebrig.pop(index)
            erledigt += 1
            speichere_personen(personen)
            speichere_warteschlange(uebrig)

            bildverwaltung = lade_bilder()
            status_map = bildverwaltung.setdefault("gesichter_status", {})
            hashwert = eintrag.get("hash")
            bildstatus = status_map.get(hashwert)
            if isinstance(bildstatus, dict):
                bildstatus["abgeschlossen"] = int(
                    bildstatus.get("abgeschlossen", 0)
                ) + 1
                if (
                    bildstatus.get("gesamt") is not None
                    and bildstatus["abgeschlossen"] >= int(bildstatus["gesamt"])
                    and not any(e.get("hash") == hashwert for e in uebrig)
                ):
                    if hashwert not in bildverwaltung.setdefault("verarbeitet", []):
                        bildverwaltung["verarbeitet"].append(hashwert)
            speichere_bilder(bildverwaltung)
        elif status == "STOP":
            break
        # Skip und fehlende Dateien bleiben in der Warteschlange.

    speichere_warteschlange(uebrig)
    return erledigt, len(uebrig)


def finde_beste_person(embedding, personen, FRUEH_ABBRUCH):
    kleinster_abstand = float("inf")
    beste_person = None

    for person in personen:
        for bild in person["bilder"]:
            abstand = np.linalg.norm(
                embedding - bild["embedding"]
            )

            #print(f"Abstand zu {person['name']}: {abstand:.3f}")
            if abstand < FRUEH_ABBRUCH:
                return person, abstand

            if abstand < kleinster_abstand:
                kleinster_abstand = abstand
                beste_person = person

    return beste_person, kleinster_abstand

def person_erweitern(person, datei, hashwert, embedding):
    embedding_array = np.asarray(embedding, dtype=np.float32)
    for bild in person.setdefault("bilder", []):
        if bild.get("hash") != hashwert or "embedding" not in bild:
            continue
        try:
            if np.linalg.norm(
                embedding_array - np.asarray(bild["embedding"], dtype=np.float32)
            ) < 1e-6:
                return False
        except (TypeError, ValueError):
            continue
    person["bilder"].append({
        "datei": str(datei),
        "hash": hashwert,
        "embedding": embedding_array
    })
    return True

def aktualisiere_bildpfade(bilddateien):
    """
    Aktualisiert gespeicherte Bildpfade anhand des SHA-256-Inhalts.
    Damit bleiben Zuordnungen erhalten, wenn Bilder verschoben oder umbenannt wurden.
    """
    personen = lade_personen()
    if not personen:
        return 0

    aktuelle_pfade = {}
    for datei in bilddateien:
        pfad = Path(datei).expanduser().resolve()
        try:
            hashwert = berechne_hash(pfad)
        except (OSError, ValueError):
            continue
        aktuelle_pfade[hashwert] = str(pfad)

    anzahl = 0
    for person in personen:
        for bild in person.get("bilder", []):
            hashwert = bild.get("hash")
            neuer_pfad = aktuelle_pfade.get(hashwert)
            if neuer_pfad and bild.get("datei") != neuer_pfad:
                bild["datei"] = neuer_pfad
                anzahl += 1

    if anzahl:
        speichere_personen(personen)

    return anzahl
