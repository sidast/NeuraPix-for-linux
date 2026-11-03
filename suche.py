import tkinter as tk
from pathlib import Path
import pickle
from PIL import Image, ImageTk
from tkinter import simpledialog, messagebox, ttk
import subprocess
import hashlib
from einstellungen import pfad_programmdatei, ordner_programmdateien, EINSTELLUNGEN
from funktionen import speichere_personen
from datenbank import erstelle_backup


def bild_anzeigen(pfad):
    fenster_bild = tk.Toplevel(fenster)
    fenster_bild.title(str(pfad.name))

    bild = Image.open(pfad)
    bild.thumbnail((1000, 800))

    bild_tk = ImageTk.PhotoImage(bild)

    label = tk.Label(
        fenster_bild,
        image=bild_tk
    )

    label.image = bild_tk
    label.pack()


AKTIVES_BILDERANSICHT_KONTEXTMENUE = None
_BILDERANSICHT_KONTEXTMENUE_BINDUNGEN = []


def _bilderansicht_kontextmenue_schliessen(event=None):
    global AKTIVES_BILDERANSICHT_KONTEXTMENUE
    global _BILDERANSICHT_KONTEXTMENUE_BINDUNGEN

    menue = AKTIVES_BILDERANSICHT_KONTEXTMENUE
    if menue is None:
        return

    AKTIVES_BILDERANSICHT_KONTEXTMENUE = None

    for sequenz, funcid in _BILDERANSICHT_KONTEXTMENUE_BINDUNGEN:
        try:
            fenster.unbind_class("all", sequenz, funcid)
        except Exception:
            pass
    _BILDERANSICHT_KONTEXTMENUE_BINDUNGEN = []

    try:
        menue.unpost()
    except tk.TclError:
        pass
    try:
        menue.destroy()
    except tk.TclError:
        pass


def _bilderansicht_kontextmenue_aussenklick(event):
    menue = AKTIVES_BILDERANSICHT_KONTEXTMENUE
    if menue is None:
        return

    widget_pfad = str(event.widget)
    menue_pfad = str(menue)
    if widget_pfad == menue_pfad or widget_pfad.startswith(menue_pfad + "."):
        return

    _bilderansicht_kontextmenue_schliessen()


def _bilderansicht_kontextmenue_fokusverlust(_event=None):
    if AKTIVES_BILDERANSICHT_KONTEXTMENUE is not None:
        _bilderansicht_kontextmenue_schliessen()


def _bilderansicht_kontextmenue_aktion(aktion):
    _bilderansicht_kontextmenue_schliessen()
    aktion()


def _bilderansicht_kontextmenue_anzeigen(event, menue):
    global AKTIVES_BILDERANSICHT_KONTEXTMENUE
    global _BILDERANSICHT_KONTEXTMENUE_BINDUNGEN

    _bilderansicht_kontextmenue_schliessen()
    AKTIVES_BILDERANSICHT_KONTEXTMENUE = menue

    for sequenz in ("<ButtonPress-1>", "<ButtonPress-2>", "<ButtonPress-3>"):
        funcid = fenster.bind_class(
            "all", sequenz, _bilderansicht_kontextmenue_aussenklick, add="+"
        )
        _BILDERANSICHT_KONTEXTMENUE_BINDUNGEN.append((sequenz, funcid))

    menue.bind("<Escape>", _bilderansicht_kontextmenue_schliessen, add="+")
    try:
        menue.tk_popup(event.x_root, event.y_root)
    except tk.TclError:
        _bilderansicht_kontextmenue_schliessen()


def kontextmenue(event, pfad, person, bild_datensatz):
    menue = tk.Menu(fenster, tearoff=0)

    menue.add_command(
        label="Bild anzeigen",
        command=lambda: _bilderansicht_kontextmenue_aktion(
            lambda: bild_anzeigen(pfad)
        )
    )

    menue.add_command(
        label="Im Ordner anzeigen",
        command=lambda: _bilderansicht_kontextmenue_aktion(
            lambda: ordner_oeffnen(pfad)
        )
    )

    menue.add_separator()

    menue.add_command(
        label="Zuordnung ändern",
        command=lambda: _bilderansicht_kontextmenue_aktion(
            lambda: bild_zuordnung_aendern(person, bild_datensatz)
        )
    )

    _bilderansicht_kontextmenue_anzeigen(event, menue)


def personen_kontextmenue(event):
    auswahl = liste.nearest(event.y)

    if auswahl < 0:
        return

    liste.selection_clear(0, tk.END)
    liste.selection_set(auswahl)

    menue = tk.Menu(fenster, tearoff=0)
    menue.add_command(
        label="Umbenennen...",
        command=lambda: _bilderansicht_kontextmenue_aktion(person_umbenennen)
    )

    _bilderansicht_kontextmenue_anzeigen(event, menue)


def ordner_oeffnen(pfad):
    subprocess.Popen([
        "nemo",
        str(pfad.parent)
    ])

def thumbnail_datei(datei):
    hashwert = hashlib.sha1(
        str(datei).encode()
    ).hexdigest()

    return THUMBNAIL_ORDNER / f"{hashwert}.jpg"


PKL_DATEI = pfad_programmdatei("personen.pkl")

THUMBNAIL_ORDNER = ordner_programmdateien() / ".thumbnails"
THUMBNAIL_ORDNER.mkdir(parents=True, exist_ok=True)


personen = []
thumbnail_cache = {}
merge_modus = False
merge_variablen = {}
merge_canvas = None
merge_inhalt = None
merge_scrollbar = None
ansicht_thumb_groesse = 150
ansicht_spalten = 4


def lade_personen():
    global personen

    try:
        with open(PKL_DATEI, "rb") as f:
            personen = pickle.load(f)

        print(f"{len(personen)} Personen geladen")

    except FileNotFoundError:
        print("Keine personen.pkl gefunden")



def personen_speichern():
    speichere_personen(personen)


def bild_zuordnung_aendern(quell_person, bild_datensatz):
    """Verschiebt genau diesen Gesichtsdatensatz zu einer bestehenden oder neuen Person."""
    dialog = tk.Toplevel(fenster)
    dialog.title("Zuordnung ändern")
    dialog.transient(fenster)
    dialog.resizable(False, False)

    rahmen = tk.Frame(dialog, padx=18, pady=14)
    rahmen.pack(fill="both", expand=True)

    tk.Label(
        rahmen,
        text=f"Aktuelle Zuordnung: {quell_person['name']}",
        font=("Arial", 10),
    ).pack(anchor="w", pady=(0, 10))

    tk.Label(
        rahmen,
        text="Bestehende Person auswählen oder neuen Namen eingeben:",
        wraplength=360,
        justify="left",
    ).pack(anchor="w", pady=(0, 5))

    eingabe = ttk.Combobox(
        rahmen,
        values=[p["name"] for p in personen],
        state="normal",
        width=38,
    )
    eingabe.pack(fill="x")
    eingabe.set(quell_person["name"])
    eingabe.focus_set()
    eingabe.selection_range(0, tk.END)

    def uebernehmen():
        ziel_name = eingabe.get().strip()
        if not ziel_name:
            messagebox.showwarning(
                "Name fehlt",
                "Bitte eine bestehende Person auswählen oder einen Namen eingeben.",
                parent=dialog,
            )
            return

        ziel_person = next(
            (
                p for p in personen
                if p["name"].strip().casefold() == ziel_name.casefold()
            ),
            None,
        )

        if ziel_person is quell_person:
            dialog.destroy()
            return

        if ziel_person is None:
            nummern = [
                int(str(p.get("label", "Person_000")).split("_")[-1])
                for p in personen
                if str(p.get("label", "")).startswith("Person_")
                and str(p.get("label", "")).split("_")[-1].isdigit()
            ]
            ziel_person = {
                "label": f"Person_{max(nummern or [0]) + 1:03d}",
                "name": ziel_name,
                "bilder": [],
            }
            personen.append(ziel_person)

        erstelle_backup("vor_zuordnungsaenderung")
        # Nur genau den angeklickten Gesichtsdatensatz verschieben.
        index = next(
            (
                i for i, eintrag in enumerate(quell_person["bilder"])
                if eintrag is bild_datensatz
            ),
            None,
        )
        if index is None:
            messagebox.showerror(
                "Zuordnung nicht geändert",
                "Der ausgewählte Bildeintrag wurde nicht mehr gefunden.",
                parent=dialog,
            )
            return

        datensatz = quell_person["bilder"].pop(index)
        ziel_person["bilder"].append(datensatz)

        # Eine Person ohne verbleibende Bilder wird aus der Liste entfernt.
        if not quell_person["bilder"]:
            quell_index = next(
                (i for i, p in enumerate(personen) if p is quell_person),
                None,
            )
            if quell_index is not None:
                personen.pop(quell_index)

        personen_speichern()
        dialog.destroy()

        zeige_personen()
        ziel_index = next(
            (i for i, p in enumerate(personen) if p is ziel_person),
            None,
        )
        if ziel_index is not None:
            liste.selection_clear(0, tk.END)
            liste.selection_set(ziel_index)
            liste.activate(ziel_index)
            liste.see(ziel_index)
            person_ausgewaehlt(None)

    button_frame = tk.Frame(rahmen)
    button_frame.pack(fill="x", pady=(12, 0))

    tk.Button(
        button_frame,
        text="Übernehmen",
        command=uebernehmen,
    ).pack(side="right", padx=(6, 0))

    tk.Button(
        button_frame,
        text="Abbrechen",
        command=dialog.destroy,
    ).pack(side="right")

    dialog.bind("<Return>", lambda event: uebernehmen())
    dialog.bind("<Escape>", lambda event: dialog.destroy())
    dialog.grab_set()
    dialog.wait_window()

def person_umbenennen():
    auswahl = liste.curselection()
    if not auswahl:
        return

    index = auswahl[0]
    person = personen[index]
    neuer_name = simpledialog.askstring(
        "Person umbenennen", "Neuer Name:",
        initialvalue=person["name"], parent=fenster
    )
    if not neuer_name or not neuer_name.strip():
        return
    neuer_name = neuer_name.strip()

    kollisions_person = next(
        (p for p in personen if p is not person and p["name"].strip().casefold() == neuer_name.casefold()),
        None,
    )
    if kollisions_person is not None:
        if not messagebox.askyesno(
            "Person existiert bereits",
            f"'{neuer_name}' existiert bereits.\n\n"
            "Sollen beide Datensätze unter diesem Namen zusammengeführt werden?",
            parent=fenster,
        ):
            return
        erstelle_backup("vor_personenzusammenfuehrung")
        kollisions_person["bilder"].extend(person["bilder"])
        personen.remove(person)
        ziel_person = kollisions_person
        ziel_name = kollisions_person["name"]
    else:
        erstelle_backup("vor_umbenennung")
        person["name"] = neuer_name
        ziel_person = person
        ziel_name = neuer_name

    personen_speichern()
    zeige_personen()
    if ziel_person in personen:
        idx = personen.index(ziel_person)
        liste.selection_set(idx)
        liste.activate(idx)
        liste.see(idx)
        person_ausgewaehlt(None)
    messagebox.showinfo("Gespeichert", f"Person heißt jetzt '{ziel_name}'.", parent=fenster)


def personen_zusammenfuehren_start():
    global merge_modus, merge_variablen, merge_frame
    if merge_modus:
        return
    merge_modus = True
    liste.pack_forget()
    zusammenfuehren_button.pack_forget()
    merge_frame = tk.Frame(personen_panel)
    merge_frame.pack(fill="both", expand=True)
    global merge_canvas, merge_inhalt, merge_scrollbar
    merge_canvas = tk.Canvas(merge_frame, highlightthickness=0)
    merge_scrollbar = ttk.Scrollbar(merge_frame, orient="vertical", command=merge_canvas.yview)
    merge_canvas.configure(yscrollcommand=merge_scrollbar.set)
    merge_scrollbar.pack(side="right", fill="y")
    merge_canvas.pack(side="left", fill="both", expand=True)
    merge_inhalt = tk.Frame(merge_canvas)
    merge_canvas.create_window((0, 0), window=merge_inhalt, anchor="nw")
    merge_inhalt.bind("<Configure>", lambda e: merge_canvas.configure(scrollregion=merge_canvas.bbox("all")))
    merge_variablen = {}
    tk.Label(merge_inhalt, text="Mindestens zwei Personen auswählen:").pack(anchor="w", pady=(0, 6))
    for person in personen:
        var = tk.BooleanVar(value=False)
        merge_variablen[id(person)] = var
        tk.Checkbutton(
            merge_inhalt,
            text=f"{person['name']} ({len(person['bilder'])} Gesichter)",
            variable=var,
            anchor="w",
        ).pack(fill="x", anchor="w")
    merge_weiter_button.pack(fill="x", pady=(8, 2))
    merge_abbrechen_button.pack(fill="x", pady=2)


def personen_zusammenfuehren_abbrechen():
    global merge_modus, merge_variablen, merge_frame
    merge_modus = False
    merge_variablen = {}
    merge_weiter_button.pack_forget()
    merge_abbrechen_button.pack_forget()
    if merge_frame is not None:
        merge_frame.destroy()
        merge_frame = None
    liste.pack(fill="both", expand=True)
    zusammenfuehren_button.pack(fill="x", pady=(8, 0))
    zeige_personen()


def personen_zusammenfuehren():
    global merge_modus
    ausgewaehlt = [
        person for person in personen
        if merge_variablen.get(id(person)) is not None and merge_variablen[id(person)].get()
    ]
    if len(ausgewaehlt) < 2:
        messagebox.showwarning("Auswahl unvollständig", "Bitte mindestens zwei Personen auswählen.", parent=fenster)
        return
    namen = [p["name"] for p in ausgewaehlt]
    if not messagebox.askyesno(
        "Zusammenführung bestätigen",
        "Diese Personen werden zusammengeführt:\n\n"
        + "\n".join(f"• {name} ({len(p['bilder'])} Gesichter)" for name, p in zip(namen, ausgewaehlt))
        + "\n\nMöchtest du fortfahren?",
        parent=fenster,
    ):
        return
    ziel_name = simpledialog.askstring(
        "Zielname festlegen",
        "Unter welchem Namen sollen die Datensätze zusammengeführt werden?",
        initialvalue=ausgewaehlt[0]["name"],
        parent=fenster,
    )
    if not ziel_name or not ziel_name.strip():
        return
    ziel_name = ziel_name.strip()

    # Wenn der Zielname bereits existiert, wird dieser Datensatz ebenfalls Ziel.
    ziel = next((p for p in personen if p["name"].strip().casefold() == ziel_name.casefold()), None)
    erstelle_backup("vor_personenzusammenfuehrung")
    if ziel is None:
        ziel = ausgewaehlt[0]
        ziel["name"] = ziel_name
    for person in ausgewaehlt:
        if person is ziel:
            continue
        ziel["bilder"].extend(person["bilder"])
        if person in personen:
            personen.remove(person)
    ziel["name"] = ziel_name
    personen_speichern()
    personen_zusammenfuehren_abbrechen()
    idx = personen.index(ziel)
    liste.selection_set(idx)
    liste.activate(idx)
    liste.see(idx)
    person_ausgewaehlt(None)
    messagebox.showinfo(
        "Zusammenführung abgeschlossen",
        f"{len(ausgewaehlt)} ausgewählte Datensätze wurden unter '{ziel_name}' vereinigt.\n"
        f"Gespeicherte Gesichter: {len(ziel['bilder'])}",
        parent=fenster,
    )


def zeige_personen():
    liste.delete(0, tk.END)
    for person in personen:
        liste.insert(tk.END, f"{person['name']}  ({len(person['bilder'])})")


def person_ausgewaehlt(event):
    auswahl = liste.curselection()

    if not auswahl:
        return

    index = auswahl[0]

    person = personen[index]

    name_label.config(
        text=f"{person['name']} - {len(person['bilder'])} Bilder"
    )

    zeige_bilder(person)



# Bildvergrößerung beim Mouseover in der Personen-Bilderansicht
_hover_preview = None
_hover_preview_job = None
_hover_preview_photo = None


def hover_preview_anzeigen(datei, x_root, y_root):
    hover_preview_schliessen()
    global _hover_preview, _hover_preview_photo, _hover_preview_job
    _hover_preview_job = None

    try:
        with Image.open(datei) as original:
            vorschau = original.convert("RGB")
            vorschau.thumbnail((650, 500), Image.Resampling.LANCZOS)
            _hover_preview_photo = ImageTk.PhotoImage(vorschau)
    except (OSError, ValueError):
        return

    _hover_preview = tk.Toplevel(fenster)
    _hover_preview.wm_overrideredirect(True)
    _hover_preview.attributes("-topmost", True)

    tk.Label(
        _hover_preview,
        image=_hover_preview_photo,
        bd=1,
        relief="solid",
        background="white",
    ).pack()

    breite, hoehe = vorschau.size
    screen_w = fenster.winfo_screenwidth()
    screen_h = fenster.winfo_screenheight()
    x = x_root + 18
    y = y_root + 18

    if x + breite > screen_w:
        x = max(0, x_root - breite - 18)
    if y + hoehe > screen_h:
        y = max(0, screen_h - hoehe - 50)

    _hover_preview.geometry(f"+{x}+{y}")


def hover_preview_start(event, datei):
    global _hover_preview_job
    hover_preview_stop()
    if not EINSTELLUNGEN.get("MOUSEOVER_AKTIV", True):
        return
    x_root, y_root = event.x_root, event.y_root
    verzoegerung = EINSTELLUNGEN.get("MOUSEOVER_VERZOEGERUNG_MS", 100)
    _hover_preview_job = fenster.after(
        verzoegerung,
        lambda pfad=datei, x=x_root, y=y_root:
            hover_preview_anzeigen(pfad, x, y),
    )


def hover_preview_stop(event=None):
    global _hover_preview_job
    if _hover_preview_job is not None:
        try:
            fenster.after_cancel(_hover_preview_job)
        except tk.TclError:
            pass
        _hover_preview_job = None
    hover_preview_schliessen()


def hover_preview_schliessen():
    global _hover_preview, _hover_preview_photo
    if _hover_preview is not None:
        try:
            _hover_preview.destroy()
        except tk.TclError:
            pass
        _hover_preview = None
    _hover_preview_photo = None



def zeige_bilder(person):
    for widget in bild_frame.winfo_children():
        widget.destroy()
    canvas.yview_moveto(0)

    spalte = 0
    zeile = 0

    for bild in person["bilder"]:

        datei = Path(bild["datei"])

        if not datei.exists():
            continue

        thumb = thumbnail_datei(datei)

        cache_key = (str(datei), ansicht_thumb_groesse)
        if cache_key in thumbnail_cache:
            img_tk = thumbnail_cache[cache_key]
        else:
            img = Image.open(datei)
            img.thumbnail(
                (ansicht_thumb_groesse, ansicht_thumb_groesse),
                Image.Resampling.LANCZOS,
            )
            img_tk = ImageTk.PhotoImage(img)
            thumbnail_cache[cache_key] = img_tk

        label = tk.Label(
            bild_frame,
            image=img_tk
        )

        label.image = img_tk


        label.bind(
            "<Button-1>",
            lambda event, pfad=datei: bild_anzeigen(pfad)
        )

        label.bind(
            "<ButtonRelease-3>",
            lambda event, pfad=datei, besitzer=person, datensatz=bild:
                kontextmenue(event, pfad, besitzer, datensatz)
        )

        label.bind(
            "<Enter>",
            lambda event, pfad=datei: hover_preview_start(event, pfad)
        )
        label.bind("<Leave>", hover_preview_stop)

        label.grid(
            row=zeile,
            column=spalte,
            padx=10,
            pady=10
        )

        spalte += 1

        if spalte >= ansicht_spalten:
            spalte = 0
            zeile += 1


def scroll_hoch(event):
    try:
        if canvas is not None and canvas.winfo_exists():
            canvas.yview_scroll(-1, "units")
    except tk.TclError:
        # Die Bilderansicht wurde möglicherweise bereits geschlossen.
        pass


def scroll_runter(event):
    try:
        if canvas is not None and canvas.winfo_exists():
            canvas.yview_scroll(1, "units")
    except tk.TclError:
        # Die Bilderansicht wurde möglicherweise bereits geschlossen.
        pass


def bilderansicht_erstellen(parent, zurueck_callback):
    """Größenadaptive Personen-/Bilderansicht im bestehenden Hauptfenster."""
    global fenster, links, rechts, liste, name_label, canvas, scrollbar
    global bild_frame, ansicht_thumb_groesse, ansicht_spalten

    fenster = parent.winfo_toplevel()
    fenster.bind("<Deactivate>", _bilderansicht_kontextmenue_fokusverlust, add="+")

    hauptbereich = tk.Frame(parent)
    hauptbereich.pack(fill="both", expand=True)
    hauptbereich.grid_rowconfigure(0, weight=1)
    hauptbereich.grid_columnconfigure(1, weight=1)

    links = tk.Frame(hauptbereich, padx=6, pady=6)
    links.grid(row=0, column=0, sticky="nsew")
    rechts = tk.Frame(hauptbereich, padx=6, pady=6)
    rechts.grid(row=0, column=1, sticky="nsew")
    rechts.grid_rowconfigure(1, weight=1)
    rechts.grid_columnconfigure(0, weight=1)

    tk.Label(links, text="Personen", font=("Arial", 12, "bold")).pack(
        anchor="w", pady=(0, 6)
    )

    global personen_panel, zusammenfuehren_button, merge_weiter_button, merge_abbrechen_button
    global merge_frame_placeholder
    personen_panel = tk.Frame(links)
    personen_panel.pack(fill="both", expand=True)
    liste = tk.Listbox(personen_panel, width=1, height=1, font=("Arial", 10))
    liste.pack(fill="both", expand=True)
    liste.bind("<<ListboxSelect>>", person_ausgewaehlt)
    liste.bind("<ButtonRelease-3>", personen_kontextmenue)

    merge_frame_placeholder = tk.Frame(personen_panel)
    zusammenfuehren_button = tk.Button(
        links, text="Personen zusammenführen", command=personen_zusammenfuehren_start
    )
    zusammenfuehren_button.pack(fill="x", pady=(8, 0))
    merge_weiter_button = tk.Button(
        links, text="Weiter", command=personen_zusammenfuehren
    )
    merge_abbrechen_button = tk.Button(
        links, text="Abbrechen", command=personen_zusammenfuehren_abbrechen
    )

    schliessen_button = tk.Button(
        links,
        text="Schließen",
        command=lambda: zurueck_callback(hauptbereich),
        font=("Arial", 10),
    )
    schliessen_button.pack(fill="x", pady=(8, 0), ipady=3)

    name_label = tk.Label(
        rechts, text="Keine Person ausgewählt",
        font=("Arial", 13, "bold"), anchor="w"
    )
    name_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))

    bildbereich = tk.Frame(rechts)
    bildbereich.grid(row=1, column=0, sticky="nsew")
    bildbereich.grid_rowconfigure(0, weight=1)
    bildbereich.grid_columnconfigure(0, weight=1)

    canvas = tk.Canvas(bildbereich, highlightthickness=0)
    scrollbar = ttk.Scrollbar(
        bildbereich, orient="vertical", command=canvas.yview
    )
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    bild_frame = tk.Frame(canvas)
    canvas_window = canvas.create_window((0, 0), window=bild_frame, anchor="nw")
    bild_frame.bind(
        "<Configure>",
        lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.bind(
        "<Configure>",
        lambda event: canvas.itemconfigure(canvas_window, width=event.width),
    )
    canvas.bind_all("<Button-4>", scroll_hoch)
    canvas.bind_all("<Button-5>", scroll_runter)

    def groesse_anpassen(event=None):
        global ansicht_thumb_groesse, ansicht_spalten

        breite = max(320, hauptbereich.winfo_width())
        hoehe = max(240, hauptbereich.winfo_height())
        faktor = max(0.65, min(1.35, min(breite / 1200, hoehe / 750)))

        neue_thumb_groesse = max(80, min(220, int(150 * faktor)))
        neue_spalten = max(
            1, min(8, int(max(100, breite - 300) / (neue_thumb_groesse + 35)))
        )
        sidebar_breite = max(145, min(310, int(breite * 0.23)))

        geaendert = (
            neue_thumb_groesse != ansicht_thumb_groesse
            or neue_spalten != ansicht_spalten
        )
        ansicht_thumb_groesse = neue_thumb_groesse
        ansicht_spalten = neue_spalten

        links.configure(width=sidebar_breite)
        links.grid_propagate(False)
        hauptbereich.grid_columnconfigure(0, minsize=sidebar_breite, weight=0)

        schrift = max(8, min(15, int(10 * faktor)))
        liste.configure(font=("Arial", schrift))
        schliessen_button.configure(font=("Arial", schrift))
        name_label.configure(font=("Arial", max(10, int(13 * faktor)), "bold"))

        if geaendert:
            auswahl = liste.curselection()
            if auswahl:
                zeige_bilder(personen[auswahl[0]])

    hauptbereich.bind("<Configure>", groesse_anpassen)
    hauptbereich.after(100, groesse_anpassen)

    lade_personen()
    zeige_personen()
    return hauptbereich
