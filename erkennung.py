from pathlib import Path
from time import perf_counter
import warnings
import cv2
from insightface.app import FaceAnalysis

from funktionen import *
from einstellungen import EINSTELLUNGEN, aktive_endungen

warnings.filterwarnings("ignore")

SCHWELLWERT = 1.2
AUTO_LERNEN = True
TRAINING = True
FRUEH_ABBRUCH = 0.5




def gesicht_in_warteschlange_speichern(datei, gesicht, embedding, hashwert):
    """Speichert ein übersprungenes Gesicht zur späteren manuellen Zuordnung."""
    warteschlange = lade_warteschlange()
    bbox = [float(x) for x in gesicht.bbox.tolist()]
    if any(e.get("hash") == hashwert and e.get("bbox") == bbox for e in warteschlange):
        return
    warteschlange.append({
        "datei": str(datei),
        "bbox": bbox,
        "embedding": embedding,
        "hash": hashwert,
    })
    speichere_warteschlange(warteschlange)
    print(f"Gesicht für spätere Zuordnung vorgemerkt: {datei}")



def bilddateien_im_ordner(ordner):
    endungen = aktive_endungen()
    return sorted(
        (datei for datei in Path(ordner).rglob("*")
         if datei.is_file() and datei.suffix.casefold() in endungen),
        key=lambda p: (str(p.parent).casefold(), p.name.casefold()),
    )



def formatiere_zeit(sekunden):
    sekunden = max(0, int(sekunden))
    stunden, rest = divmod(sekunden, 3600)
    minuten, sekunden = divmod(rest, 60)
    if stunden:
        return f"{stunden} h {minuten:02d} min"
    if minuten:
        return f"{minuten} min {sekunden:02d} s"
    return f"{sekunden} s"


def bilder_analysieren(ordner, fortschritt, status_bild, restzeit_label, karussell, ergebnis_label, STOP, hauptfenster, namens_frame, hintergrund_status=None):
    status_bild.config(text="Analyse wird gestartet …")
    hauptfenster.update()
    schwellwert = float(EINSTELLUNGEN.get("ERKENNUNGSSCHWELLE", 1.2))
    app = FaceAnalysis(name="buffalo_l")
    app.prepare(ctx_id=0)
    print("Gesichtserkennung geladen")

    if isinstance(ordner, (str, Path)):
        ordner = [ordner]
    ordner = [Path(p).expanduser() for p in ordner]
    bilder = []
    bekannte_hashes = set()
    for stammordner in ordner:
        if not stammordner.is_dir():
            print(f"Analyseordner nicht gefunden: {stammordner}")
            continue
        for datei in bilddateien_im_ordner(stammordner):
            try:
                hashwert = berechne_hash(datei)
            except OSError:
                continue
            if hashwert not in bekannte_hashes:
                bekannte_hashes.add(hashwert)
                bilder.append(datei)
    bilder.sort(key=lambda p: (str(p.parent).casefold(), p.name.casefold()))
    print(f"{len(bilder)} eindeutige Bilder in {len(ordner)} Analyseordnern gefunden")

    personen = lade_personen()
    bildverwaltung = lade_bilder()
    naechste_person = max(
        [int(p.get("label", "Person_000").split("_")[-1]) for p in personen if str(p.get("label", "")).startswith("Person_")] or [0]
    ) + 1

    if not TRAINING:
        return

    # Vor dem Start bereits erledigte oder verworfene Bilder herausfiltern.
    # Dadurch wird beim Fortsetzen direkt mit dem ersten offenen Bild begonnen.
    erledigt = set(bildverwaltung.get("verarbeitet", []))
    verworfen = set(bildverwaltung.get("verworfen", []))
    offene_bilder = []
    for original_index, datei in enumerate(bilder):
        hashwert = berechne_hash(datei)
        if hashwert not in erledigt and hashwert not in verworfen:
            offene_bilder.append((original_index, datei, hashwert))

    fortschritt["maximum"] = max(len(offene_bilder), 1)
    fortschritt["value"] = 0
    if not offene_bilder:
        status_bild.config(text="Alle Bilder wurden bereits analysiert")
        restzeit_label.config(text="")
        hauptfenster.update()
        speichere_personen(personen)
        speichere_bilder(bildverwaltung)
        return

    import queue
    import threading

    # Alle offenen Bilder werden unabhängig von der GUI voranalysiert.
    # Der Worker greift ausschließlich auf OpenCV und InsightFace zu.
    ergebnis_queue = queue.Queue()

    def voranalyse_worker():
        try:
            for original_index, datei, hashwert in offene_bilder:
                if STOP["abbrechen"]:
                    break
                try:
                    bild_cv = cv2.imread(str(datei))
                    if bild_cv is None:
                        ergebnis_queue.put(
                            (original_index, datei, hashwert, None, "Bild nicht lesbar", None)
                        )
                        continue

                    # Misst die tatsächliche InsightFace-Zeit für das erste Bild.
                    vektor_start = perf_counter()
                    gesichter = app.get(bild_cv)
                    vektorzeit = perf_counter() - vektor_start

                    # Relativer Filter: Gesichtsbreite im Verhältnis zum breitesten Gesicht dieses Bildes.
                    if gesichter:
                        max_breite = max(float(g.bbox[2] - g.bbox[0]) for g in gesichter)
                        mindest_prozent = float(EINSTELLUNGEN.get("MIN_GESICHTSGROESSE_PROZENT", 0))
                        if mindest_prozent > 0 and max_breite > 0:
                            grenze = max_breite * mindest_prozent / 100.0
                            gesichter = [
                                g for g in gesichter
                                if float(g.bbox[2] - g.bbox[0]) >= grenze
                            ]
                    ergebnis_queue.put(
                        (original_index, datei, hashwert, gesichter, None, vektorzeit)
                    )
                except Exception as exc:
                    ergebnis_queue.put(
                        (original_index, datei, hashwert, None, str(exc), None)
                    )
        finally:
            ergebnis_queue.put(None)

    # Restzeit: Referenz ist die gemessene InsightFace-Zeit des ersten Bildes.
    eta = {
        "referenz": None,
        "rest": None,
        "letzter_tick": perf_counter(),
        "job": None,
        "letzter_text": None,
    }

    def eta_anzeigen():
        if eta["referenz"] is None:
            text = "Restzeit: wird nach dem ersten Bild berechnet …"
        else:
            text = f"Voraussichtliche Restzeit: ca. {formatiere_zeit(eta['rest'])}"
        if text != eta["letzter_text"]:
            restzeit_label.config(text=text)
            eta["letzter_text"] = text

    def eta_tick():
        jetzt = perf_counter()
        vergangen = max(0.0, jetzt - eta["letzter_tick"])
        eta["letzter_tick"] = jetzt

        # Während das Namensfenster sichtbar ist, wird keine Zeit abgezogen.
        try:
            # Das Namensfenster ist ein modales Toplevel und hält den Grab.
            namensfenster_offen = hauptfenster.grab_current() is not None
        except Exception:
            namensfenster_offen = False

        if eta["rest"] is not None and not namensfenster_offen:
            eta["rest"] = max(0.0, eta["rest"] - vergangen)
            eta_anzeigen()

        try:
            eta["job"] = hauptfenster.after(100, eta_tick)
        except Exception:
            eta["job"] = None

    def eta_neu_berechnen(vektorzeit, verbleibende_bilder):
        if eta["referenz"] is None and vektorzeit is not None:
            eta["referenz"] = max(0.0, float(vektorzeit))
        if eta["referenz"] is not None:
            eta["rest"] = eta["referenz"] * max(0, verbleibende_bilder)
            eta["letzter_tick"] = perf_counter()
            eta_anzeigen()

    eta_anzeigen()
    eta["job"] = hauptfenster.after(100, eta_tick)

    worker = threading.Thread(
        target=voranalyse_worker,
        name="FotoKI-Voranalyse",
        daemon=True,
    )
    worker.start()

    gesamtzeit_analyse = 0.0
    anzahl_zeitmessungen = 0

    for lauf_index in range(1, len(offene_bilder) + 1):
        if STOP["abbrechen"]:
            break

        # Auf das nächste vorbereitete Ergebnis warten, ohne die GUI einzufrieren.
        while True:
            if STOP["abbrechen"]:
                break
            try:
                vorbereitet = ergebnis_queue.get(timeout=0.1)
                break
            except queue.Empty:
                hauptfenster.update()

        if STOP["abbrechen"] or vorbereitet is None:
            break

        original_index, datei, hashwert, gesichter, analyse_fehler, vektorzeit = vorbereitet
        bild_start = perf_counter()
        dialogzeit = 0.0
        print(datei)

        if analyse_fehler:
            print(f"Bild übersprungen: {datei} ({analyse_fehler})")
            eta_neu_berechnen(vektorzeit, len(offene_bilder) - lauf_index)
            continue

        bild_cv = cv2.imread(str(datei))
        if bild_cv is None:
            print(f"Bild konnte nach der Voranalyse nicht erneut geladen werden: {datei}")
            continue

        karussell.zeige(
            bilder, original_index, bild_cv=bild_cv, animieren=(lauf_index > 1)
        )
        status_bild.config(text=f"Analysiere Bild {lauf_index}/{len(offene_bilder)}")
        fortschritt["value"] = lauf_index
        eta_neu_berechnen(vektorzeit, len(offene_bilder) - lauf_index)
        hauptfenster.update()

        if not gesichter:
            hauptfenster.update()
            continue

        bild_fertig = True
        gesichter_abgeschlossen = 0
        skip_rest_ausgefuehrt = False
        print("Anzahl berücksichtigter Gesichter:", len(gesichter))

        for gesicht in gesichter:
            if STOP["abbrechen"]:
                speichere_personen(personen)
                speichere_bilder(bildverwaltung)
                worker.join(timeout=2.0)
                return

            bild_markiert = bild_cv.copy()
            x1, y1, x2, y2 = gesicht.bbox.astype(int)
            cv2.rectangle(bild_markiert, (x1, y1), (x2, y2), (0, 255, 0), 3)
            karussell.zeige(
                bilder, original_index, bild_cv=bild_markiert, animieren=False
            )
            hauptfenster.update()

            embedding = gesicht.normed_embedding
            if len(personen) == 0:
                dialog_start = perf_counter()
                naechste_person, status = neue_person_anlegen(
                    datei, gesicht, embedding, hashwert, personen,
                    naechste_person, hauptfenster, namens_frame, STOP,
                    in_warteschlange=bool(hintergrund_status and hintergrund_status()),
                )
                dialogzeit += perf_counter() - dialog_start
                if status == "QUEUED":
                    hauptfenster.update_idletasks()
                    continue
                if status == "STOP":
                    speichere_personen(personen)
                    speichere_bilder(bildverwaltung)
                    worker.join(timeout=2.0)
                    if eta["job"] is not None:
                        try:
                            hauptfenster.after_cancel(eta["job"])
                        except Exception:
                            pass
                        eta["job"] = None
                    return
                if status == "SKIP":
                    gesicht_in_warteschlange_speichern(
                        datei, gesicht, embedding, hashwert
                    )
                    bild_fertig = False
                    continue
                if status == "VERWERFEN":
                    bildverwaltung["verworfen"].append(hashwert)
                    speichere_bilder(bildverwaltung)
                    bild_fertig = False
                    break
                if status == "SKIP_REST":
                    bild_fertig = False
                    skip_rest_ausgefuehrt = True
                    break
                gesichter_abgeschlossen += 1
                continue

            beste_person, kleinster_abstand = finde_beste_person(
                embedding, personen, FRUEH_ABBRUCH
            )

            if beste_person is not None and kleinster_abstand < schwellwert:
                if EINSTELLUNGEN.get("STATUSLEISTE_AKTIV", True):
                    ergebnis_label.config(
                        text=f"{beste_person['name']} erkannt\\nAbstand: {kleinster_abstand:.3f}"
                    )
                if AUTO_LERNEN:
                    person_erweitern(beste_person, datei, hashwert, embedding)
                    print(f"{datei.stem} wurde {beste_person['name']} zugeordnet und gelernt.")
                gesichter_abgeschlossen += 1
            else:
                if EINSTELLUNGEN.get("STATUSLEISTE_AKTIV", True):
                    ergebnis_label.config(text="Neue Person erkannt")
                dialog_start = perf_counter()
                naechste_person, status = neue_person_anlegen(
                    datei, gesicht, embedding, hashwert, personen,
                    naechste_person, hauptfenster, namens_frame, STOP,
                    in_warteschlange=bool(hintergrund_status and hintergrund_status()),
                )
                dialogzeit += perf_counter() - dialog_start
                if status == "QUEUED":
                    hauptfenster.update_idletasks()
                    continue
                if status == "STOP":
                    speichere_personen(personen)
                    speichere_bilder(bildverwaltung)
                    worker.join(timeout=2.0)
                    if eta["job"] is not None:
                        try:
                            hauptfenster.after_cancel(eta["job"])
                        except Exception:
                            pass
                        eta["job"] = None
                    return
                if status == "SKIP":
                    gesicht_in_warteschlange_speichern(
                        datei, gesicht, embedding, hashwert
                    )
                    bild_fertig = False
                    continue
                if status == "VERWERFEN":
                    bildverwaltung["verworfen"].append(hashwert)
                    speichere_bilder(bildverwaltung)
                    bild_fertig = False
                    break
                if status == "SKIP_REST":
                    bild_fertig = False
                    skip_rest_ausgefuehrt = True
                    break
                gesichter_abgeschlossen += 1

            hauptfenster.update()

        status_map = bildverwaltung.setdefault("gesichter_status", {})
        status_map[hashwert] = {
            "gesamt": len(gesichter),
            "abgeschlossen": gesichter_abgeschlossen,
        }

        # Falls ein Skip noch während desselben Bildes automatisch zugeordnet wurde,
        # ist der Warteschlangeneintrag bereits verschwunden. Dann ist das Bild fertig.
        warteschlangen_hashes = {
            eintrag.get("hash") for eintrag in lade_warteschlange()
        }
        if (
            not skip_rest_ausgefuehrt
            and hashwert not in warteschlangen_hashes
            and hashwert not in bildverwaltung.get("verworfen", [])
        ):
            status_map[hashwert]["abgeschlossen"] = len(gesichter)
            bild_fertig = True

        if bild_fertig and hashwert not in bildverwaltung["verarbeitet"]:
            bildverwaltung["verarbeitet"].append(hashwert)
        speichere_bilder(bildverwaltung)
        speichere_personen(personen)

        hauptfenster.update()

    if STOP["abbrechen"]:
        worker.join(timeout=2.0)

    if eta["job"] is not None:
        try:
            hauptfenster.after_cancel(eta["job"])
        except Exception:
            pass
        eta["job"] = None

    restzeit_label.config(text="")
    speichere_personen(personen)
    speichere_bilder(bildverwaltung)
    for person in personen:
        print(person["name"], len(person["bilder"]))

def einzelbild_analysieren(datei, hauptfenster, STOP=None):
    schwellwert = float(EINSTELLUNGEN.get("ERKENNUNGSSCHWELLE", 1.2))
    """Analysiert ausschließlich ein ausgewähltes Bild und fragt jedes Gesicht ab."""
    datei = Path(datei)
    if not datei.is_file():
        return {"status": "datei_fehlt", "zugeordnet": 0, "gesichter": 0}

    bild_cv = cv2.imread(str(datei))
    if bild_cv is None:
        return {"status": "nicht_lesbar", "zugeordnet": 0, "gesichter": 0}

    hashwert = berechne_hash(datei)
    warteschlangen_eintraege = [
        eintrag for eintrag in lade_warteschlange()
        if eintrag.get("hash") == hashwert
    ]

    if warteschlangen_eintraege:
        # Gesichtsvektoren und Bounding Boxes aus der bereits erfolgten Analyse nutzen.
        gesichter = [
            SimpleNamespace(
                bbox=np.asarray(eintrag["bbox"], dtype=np.float32),
                normed_embedding=np.asarray(eintrag["embedding"], dtype=np.float32),
            )
            for eintrag in warteschlangen_eintraege
            if "bbox" in eintrag and "embedding" in eintrag
        ]
        print(f"{len(gesichter)} gespeicherte Gesichtsvektoren für Einzelbildanalyse wiederverwendet.")
    else:
        app = FaceAnalysis(name="buffalo_l")
        app.prepare(ctx_id=0)
        print("Gesichtserkennung für Einzelbildanalyse geladen")
        gesichter = app.get(bild_cv)

    if not gesichter:
        return {"status": "kein_gesicht", "zugeordnet": 0, "gesichter": 0}

    if gesichter:
        max_breite = max(float(g.bbox[2] - g.bbox[0]) for g in gesichter)
        mindest_prozent = float(EINSTELLUNGEN.get("MIN_GESICHTSGROESSE_PROZENT", 0))
        if mindest_prozent > 0 and max_breite > 0:
            grenze = max_breite * mindest_prozent / 100.0
            gesichter = [
                g for g in gesichter
                if float(g.bbox[2] - g.bbox[0]) >= grenze
            ]
    if not gesichter:
        return {"status": "kein_gesicht_groessengrenze", "zugeordnet": 0, "gesichter": 0}

    personen = lade_personen()
    bildverwaltung = lade_bilder()
    bildverwaltung.setdefault("verarbeitet", [])
    bildverwaltung.setdefault("verworfen", [])
    naechste_person = max(
        [
            int(p.get("label", "Person_000").split("_")[-1])
            for p in personen
            if str(p.get("label", "")).startswith("Person_")
        ] or [0]
    ) + 1

    stop_status = STOP if STOP is not None else {"abbrechen": False}
    stop_status["abbrechen"] = False
    zugeordnet = 0
    uebersprungen = False

    for gesicht in gesichter:
        embedding = gesicht.normed_embedding
        beste_person, abstand = finde_beste_person(
            embedding, personen, FRUEH_ABBRUCH
        )
        bekannter_name = (
            beste_person["name"]
            if beste_person is not None and abstand < schwellwert
            else None
        )

        personen_vorher = {
            id(person): len(person["bilder"])
            for person in personen
        }

        naechste_person, status = neue_person_anlegen(
            datei,
            gesicht,
            embedding,
            hashwert,
            personen,
            naechste_person,
            hauptfenster,
            None,
            stop_status,
            vorausgefuellter_name=bekannter_name,
            einzelbild=True,
        )

        if status == "STOP":
            speichere_personen(personen)
            return {
                "status": "gestoppt",
                "zugeordnet": zugeordnet,
                "gesichter": len(gesichter),
            }

        if status == "SKIP":
            uebersprungen = True
            continue

        if status == "SKIP_REST":
            uebersprungen = True
            break

        if status == "VERWERFEN":
            if hashwert not in bildverwaltung["verworfen"]:
                bildverwaltung["verworfen"].append(hashwert)
            if hashwert in bildverwaltung["verarbeitet"]:
                bildverwaltung["verarbeitet"].remove(hashwert)
            speichere_bilder(bildverwaltung)
            speichere_personen(personen)
            return {
                "status": "verworfen",
                "zugeordnet": zugeordnet,
                "gesichter": len(gesichter),
            }

        if status == "OK":
            # Ermitteln, welcher Person der Dialog gerade einen Eintrag hinzugefügt hat.
            ziel_person = next(
                (
                    person for person in personen
                    if len(person["bilder"]) > personen_vorher.get(id(person), 0)
                ),
                None,
            )

            # Eine alte Zuordnung desselben Gesichts (gleiche Datei + gleicher Vektor)
            # entfernen. Der gerade bestätigte Eintrag bleibt genau einmal erhalten.
            behalten = False
            for person in personen:
                neue_bilder = []
                for eintrag in person["bilder"]:
                    gleicher_vektor = (
                        eintrag.get("hash") == hashwert
                        and np.linalg.norm(
                            np.asarray(eintrag["embedding"]) - embedding
                        ) < 1e-6
                    )
                    if gleicher_vektor:
                        if person is ziel_person and not behalten:
                            neue_bilder.append(eintrag)
                            behalten = True
                    else:
                        neue_bilder.append(eintrag)
                person["bilder"] = neue_bilder

            zugeordnet += 1
            speichere_personen(personen)
            automatisch_zugeordnet = warteschlange_mit_personen_abgleichen(
                personen, schwellwert
            )
            if automatisch_zugeordnet:
                print(
                    f"{automatisch_zugeordnet} weitere Warteschlangengesichter "
                    "automatisch zugeordnet."
                )

    if not uebersprungen and zugeordnet == len(gesichter):
        if hashwert in bildverwaltung["verworfen"]:
            bildverwaltung["verworfen"].remove(hashwert)
        if hashwert not in bildverwaltung["verarbeitet"]:
            bildverwaltung["verarbeitet"].append(hashwert)

    speichere_personen(personen)
    speichere_bilder(bildverwaltung)
    return {
        "status": "ok",
        "zugeordnet": zugeordnet,
        "gesichter": len(gesichter),
    }

