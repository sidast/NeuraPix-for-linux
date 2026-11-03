import shutil
import os
from datetime import datetime
import subprocess
import sys
import threading
import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw
# GTK3 StatusIcon statt pystray: pystray._xorg hat hier kein Kontextmenü.
try:
    import gi
except ImportError:
    system_dist = Path("/usr/lib/python3/dist-packages")
    if system_dist.is_dir():
        sys.path.append(str(system_dist))
    try:
        import gi
    except ImportError:
        gi = None

if gi is not None:
    try:
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, GLib
    except Exception:
        Gtk = None
        GLib = None
else:
    Gtk = None
    GLib = None
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from erkennung import bilder_analysieren, einzelbild_analysieren
from einstellungen import (
    EINSTELLUNGEN,
    ordner_programmdateien,
    speichere_einstellungen,
    BILDFORMATE,
    aktive_endungen,
)
from karussell import BilderKarussell
from funktionen import (
    aktualisiere_bildpfade, warteschlange_anzahl, warteschlange_bearbeiten,
    lade_warteschlange, berechne_hash,
)
from datenbank import (erstelle_backup, pruefe_datenbank, finde_dateiduplikate, exportiere_datenbank, stelle_datenbank_wieder_her)


APP_NAME = "NeuraPix"
APP_SUBTITLE = "Gar nicht mal so unintelligente Bildverwaltung"
BRANDING_DIR = Path(__file__).resolve().parent / "branding"
APP_ICON = BRANDING_DIR / "hicolor" / "256x256" / "apps" / "neurapix.png"

def _set_app_icon(window):
    try:
        if APP_ICON.is_file():
            icon = ImageTk.PhotoImage(Image.open(APP_ICON).convert("RGBA"))
            window.iconphoto(True, icon)
            window._neurapix_icon_ref = icon
    except Exception:
        pass

def _modernisiere_ttk(root):
    """Einheitliches NeuraPix-Design für Tk- und ttk-Widgets."""
    c = {"bg": "#EAF0FC", "white": "#FFFFFF", "blue": "#3157C8",
         "blue_hover": "#2446AA", "text": "#17233F", "muted": "#65728B",
         "border": "#DCE4F2", "selected": "#DCE7FF", "navy": "#17264A"}
    root.configure(background=c["bg"])
    defaults = {
        "*Background": c["bg"], "*Foreground": c["text"], "*Font": ("DejaVu Sans", 9),
        "*Label.Background": c["bg"], "*Label.Foreground": c["text"],
        "*Button.Background": c["blue"], "*Button.Foreground": "#FFFFFF",
        "*Button.ActiveBackground": c["blue_hover"], "*Button.ActiveForeground": "#FFFFFF",
        "*Button.DisabledForeground": "#AAB4C7", "*Button.Relief": "flat",
        "*Button.BorderWidth": 0, "*Button.Cursor": "hand2", "*Button.Padx": 12, "*Button.Pady": 7,
        "*Frame.Background": c["bg"], "*Labelframe.Background": c["bg"],
        "*Labelframe.Foreground": c["text"], "*Entry.Background": c["white"],
        "*Entry.Foreground": c["text"], "*Entry.InsertBackground": c["blue"],
        "*Listbox.Background": c["white"], "*Listbox.Foreground": c["text"],
        "*Listbox.SelectBackground": c["blue"], "*Listbox.SelectForeground": "#FFFFFF",
        "*Text.Background": c["white"], "*Text.Foreground": c["text"],
        "*Checkbutton.Background": c["bg"], "*Checkbutton.Foreground": c["text"],
        "*Radiobutton.Background": c["bg"], "*Radiobutton.Foreground": c["text"],
        "*Scale.Background": c["bg"], "*Menu.Background": c["white"],
        "*Menu.Foreground": c["text"], "*Menu.ActiveBackground": c["blue"],
        "*Menu.ActiveForeground": "#FFFFFF", "*Menu.BorderWidth": 0, "*Menu.Relief": "flat"}
    for option, value in defaults.items():
        root.option_add(option, value)
    try:
        s = ttk.Style(root)
        if "clam" in s.theme_names():
            s.theme_use("clam")
        s.configure(".", font=("DejaVu Sans", 9), background=c["bg"], foreground=c["text"])
        s.configure("TFrame", background=c["bg"])
        s.configure("TLabel", background=c["bg"], foreground=c["text"], padding=2)
        s.configure("Title.TLabel", background=c["bg"], foreground=c["navy"],
                    font=("DejaVu Sans", 16, "bold"))
        s.configure("Secondary.TLabel", background=c["bg"], foreground=c["muted"])
        s.configure("TButton", padding=(12, 7), background=c["blue"],
                    foreground="#FFFFFF", borderwidth=0, focusthickness=0)
        s.map("TButton", background=[("active", c["blue_hover"]), ("pressed", c["navy"]),
                                     ("disabled", "#B9C5DC")])
        s.configure("Secondary.TButton", padding=(12, 7), background="#E5ECFA",
                    foreground=c["navy"], borderwidth=0)
        s.map("Secondary.TButton", background=[("active", "#D5E1F8")])
        s.configure("TEntry", padding=6, fieldbackground=c["white"],
                    foreground=c["text"], bordercolor=c["border"])
        s.configure("TCombobox", padding=5, fieldbackground=c["white"],
                    foreground=c["text"], arrowcolor=c["blue"])
        s.configure("TCheckbutton", background=c["bg"], foreground=c["text"])
        s.configure("TRadiobutton", background=c["bg"], foreground=c["text"])
        s.configure("TScale", background=c["bg"], troughcolor=c["border"])
        s.configure("TProgressbar", thickness=9, troughcolor=c["border"],
                    background=c["blue"], bordercolor=c["border"])
        s.configure("Treeview", rowheight=30, font=("DejaVu Sans", 9),
                    background=c["white"], fieldbackground=c["white"],
                    foreground=c["text"], borderwidth=0)
        s.configure("Treeview.Heading", font=("DejaVu Sans", 9, "bold"),
                    background="#E8EEF9", foreground=c["navy"], padding=7)
        s.map("Treeview", background=[("selected", c["selected"])],
              foreground=[("selected", c["navy"])])
    except Exception:
        pass


def _bild_mit_abgerundeten_ecken(bild, radius=12):
    """Gibt ein RGBA-Thumbnail mit transparent abgerundeten Ecken zurück."""
    bild = bild.convert("RGBA")
    maske = Image.new("L", bild.size, 0)
    zeichner = ImageDraw.Draw(maske)
    zeichner.rounded_rectangle((0, 0, bild.width - 1, bild.height - 1), radius=radius, fill=255)
    bild.putalpha(maske)
    return bild


aktueller_ordner = None
analyse_ordner = [
    str(Path(p).expanduser())
    for p in EINSTELLUNGEN.get("ANALYSE_ORDNER", [])
    if Path(p).expanduser().is_dir()
]
STOP = {"abbrechen": False}
thumbnail_refs = []
thumbnail_job = None
thumbnail_dateien = []
thumbnail_index = 0
THUMBNAILS_PRO_BATCH = 10
VERSION = "1.0.0"
ANALYSE_LAEUFT = False
SCHLIESSEN_ANGEFORDERT = False
TRAY_ICON = None
TRAY_THREAD = None
TRAY_LOOP = None
TRAY_START_EVENT = None
TRAY_START_RESULT = False
ECHT_BEENDEN = False
STARTANSICHT = True
WARTESCHLANGE_ANSICHT = False


def bilddateien_im_ordner(ordner):
    endungen = aktive_endungen()
    return sorted(
        (datei for datei in Path(ordner).rglob("*")
         if datei.is_file() and datei.suffix.casefold() in endungen),
        key=lambda p: (str(p.parent).casefold(), p.name.casefold()),
    )


def zentriere_fenster(prozent):
    """Setzt die Fenstergröße relativ zur Bildschirmauflösung und zentriert es."""
    fenster.update_idletasks()
    breite = max(1, int(fenster.winfo_screenwidth() * prozent))
    hoehe = max(1, int(fenster.winfo_screenheight() * prozent))
    x = max(0, (fenster.winfo_screenwidth() - breite) // 2)
    y = max(0, (fenster.winfo_screenheight() - hoehe) // 2)
    fenster.geometry(f"{breite}x{hoehe}+{x}+{y}")


def hauptoberflaeche_anzeigen():
    global STARTANSICHT
    STARTANSICHT = False
    start_frame.destroy()
    fenster.config(menu=menueleiste)
    ordner_info.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
    karussell_frame.grid(row=1, column=0, sticky="nsew")
    fortschritt_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
    button_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=(4, 10))
    if EINSTELLUNGEN["STATUSLEISTE_AKTIV"]:
        ergebnis_label.grid(row=4, column=0, sticky="ew", padx=10, pady=3)
    zentriere_fenster(0.85)


def alle_analysebilder():
    bilder = []
    gesehen = set()
    for ordner in analyse_ordner:
        pfad = Path(ordner).expanduser()
        if not pfad.is_dir():
            continue
        for datei in bilddateien_im_ordner(pfad):
            try:
                hashwert = berechne_hash(datei)
            except OSError:
                continue
            if hashwert not in gesehen:
                gesehen.add(hashwert)
                bilder.append(datei)
    return sorted(bilder, key=lambda p: (str(p.parent).casefold(), p.name.casefold()))


def analyseordner_info_aktualisieren():
    bilder = alle_analysebilder()
    if not analyse_ordner:
        text = "Bitte Analyseordner hinzufügen"
    else:
        text = f"{len(analyse_ordner)} Analyseordner · {len(bilder)} eindeutige Bilder"
    ordner_info.config(text=text)
    analyse_button.config(state="normal" if bilder else "disabled")
    return bilder


def ordner_auswaehlen():
    global aktueller_ordner
    ordner = filedialog.askdirectory(parent=fenster, title="Analyseordner hinzufügen")
    if not ordner:
        return
    pfad = str(Path(ordner).expanduser().resolve())
    if pfad not in analyse_ordner:
        analyse_ordner.append(pfad)
    aktueller_ordner = Path(pfad)
    EINSTELLUNGEN["ANALYSE_ORDNER"] = list(analyse_ordner)
    speichere_einstellungen(EINSTELLUNGEN)
    if STARTANSICHT:
        hauptoberflaeche_anzeigen()
    bilder = analyseordner_info_aktualisieren()
    STOP["abbrechen"] = False
    namens_frame.grid_remove()
    zeige_thumbnails(bilder)
    fenster.update_idletasks()
    try:
        aktualisierte_pfade = aktualisiere_bildpfade(bilder)
        if aktualisierte_pfade:
            print(f"{aktualisierte_pfade} Bildpfad(e) nach Verschieben/Umbenennen aktualisiert.")
    except Exception as exc:
        print(f"Warnung: Bildpfade konnten nicht abgeglichen werden: {exc}")


def analyseordner_verwalten():
    global aktueller_ordner, analyse_ordner

    dialog = tk.Toplevel(fenster)
    dialog.title("Analyseordner verwalten")
    dialog.transient(fenster)
    dialog.geometry("620x300")

    tk.Label(
        dialog,
        text="Ordner, die gemeinsam analysiert werden:"
    ).pack(anchor="w", padx=12, pady=(12, 4))

    liste = tk.Listbox(dialog, selectmode="extended", width=85, height=10)
    liste.pack(fill="both", expand=True, padx=12, pady=4)

    auswahl_ordner = list(analyse_ordner)

    def liste_aktualisieren():
        liste.delete(0, "end")
        for pfad in auswahl_ordner:
            liste.insert("end", pfad)

    def hinzufuegen():
        pfad = filedialog.askdirectory(
            parent=dialog,
            title="Analyseordner hinzufügen"
        )
        if pfad:
            pfad = str(Path(pfad).expanduser().resolve())
            if pfad not in auswahl_ordner:
                auswahl_ordner.append(pfad)
                liste_aktualisieren()

    def entfernen():
        for index in reversed(liste.curselection()):
            pfad = liste.get(index)
            if pfad in auswahl_ordner:
                auswahl_ordner.remove(pfad)
        liste_aktualisieren()

    knoepfe = tk.Frame(dialog)
    knoepfe.pack(fill="x", padx=12, pady=8)

    tk.Button(
        knoepfe, text="Hinzufügen…", command=hinzufuegen
    ).pack(side="left")

    tk.Button(
        knoepfe, text="Auswahl entfernen", command=entfernen
    ).pack(side="left", padx=6)

    def uebernehmen():
        global analyse_ordner, aktueller_ordner

        analyse_ordner = list(auswahl_ordner)
        EINSTELLUNGEN["ANALYSE_ORDNER"] = list(analyse_ordner)
        speichere_einstellungen(EINSTELLUNGEN)

        aktueller_ordner = (
            Path(analyse_ordner[0]) if analyse_ordner else None
        )

        if STARTANSICHT and analyse_ordner:
            hauptoberflaeche_anzeigen()

        bilder = analyseordner_info_aktualisieren()
        zeige_thumbnails(bilder)

        dialog.destroy()

    tk.Button(
        knoepfe, text="Übernehmen", command=uebernehmen
    ).pack(side="right")

    tk.Button(
        knoepfe, text="Abbrechen", command=dialog.destroy
    ).pack(side="right", padx=6)

    liste_aktualisieren()

    dialog.update_idletasks()
    dialog.wait_visibility()
    dialog.grab_set()


# Bildvergrößerung beim Mouseover in der Thumbnail-Vorschau
_hover_preview = None
_hover_preview_job = None
_hover_preview_photo = None


def _hover_preview_anzeigen(datei, x_root, y_root):
    _hover_preview_schliessen()
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

    label = tk.Label(
        _hover_preview,
        image=_hover_preview_photo,
        bd=1,
        relief="solid",
        background="white",
    )
    label.pack()

    breite = vorschau.width
    hoehe = vorschau.height
    screen_w = fenster.winfo_screenwidth()
    screen_h = fenster.winfo_screenheight()

    x = x_root + 18
    y = y_root + 18
    if x + breite > screen_w:
        x = max(0, x_root - breite - 18)
    if y + hoehe > screen_h:
        y = max(0, screen_h - hoehe - 50)

    _hover_preview.geometry(f"+{x}+{y}")


def _hover_preview_start(event, datei):
    global _hover_preview_job
    _hover_preview_stop()
    if not EINSTELLUNGEN.get("MOUSEOVER_AKTIV", True):
        return
    x_root, y_root = event.x_root, event.y_root
    verzoegerung = EINSTELLUNGEN.get("MOUSEOVER_VERZOEGERUNG_MS", 100)
    _hover_preview_job = fenster.after(
        verzoegerung,
        lambda pfad=datei, x=x_root, y=y_root:
            _hover_preview_anzeigen(pfad, x, y),
    )


def _hover_preview_stop(event=None):
    global _hover_preview_job
    if _hover_preview_job is not None:
        try:
            fenster.after_cancel(_hover_preview_job)
        except tk.TclError:
            pass
        _hover_preview_job = None
    _hover_preview_schliessen()


def _hover_preview_schliessen():
    global _hover_preview, _hover_preview_photo
    if _hover_preview is not None:
        try:
            _hover_preview.destroy()
        except tk.TclError:
            pass
        _hover_preview = None
    _hover_preview_photo = None


def _thumbnail_hover_binden(widget, datei):
    widget.bind(
        "<Enter>",
        lambda event, pfad=datei: _hover_preview_start(event, pfad),
    )
    widget.bind("<Leave>", _hover_preview_stop)


def zeige_thumbnails(bilder):
    """Zeigt Thumbnails portionsweise; die GUI bleibt währenddessen bedienbar."""
    global thumbnail_refs, thumbnail_job, thumbnail_dateien, thumbnail_index
    if thumbnail_job is not None:
        try:
            fenster.after_cancel(thumbnail_job)
        except tk.TclError:
            pass
        thumbnail_job = None
    thumbnail_refs = []
    thumbnail_dateien = list(bilder)
    thumbnail_index = 0
    karussell.canvas.grid_remove()
    for widget in thumbnail_inhalt.winfo_children():
        widget.destroy()

    if not thumbnail_dateien:
        tk.Label(thumbnail_inhalt, text="Keine Bilder gefunden").grid(row=0, column=0, padx=12, pady=12)
        thumbnail_canvas.grid()
        thumbnail_scrollbar.grid()
        return

    thumbnail_canvas.grid()
    thumbnail_scrollbar.grid()
    thumbnail_inhalt.update_idletasks()
    _thumbnails_naechster_batch()


def _thumbnails_naechster_batch():
    global thumbnail_job, thumbnail_index
    spalten = 5
    ende = min(thumbnail_index + THUMBNAILS_PRO_BATCH, len(thumbnail_dateien))
    for index in range(thumbnail_index, ende):
        datei = thumbnail_dateien[index]
        try:
            with Image.open(datei) as original:
                bild = original.convert("RGB")
                bild.thumbnail((132, 94), Image.Resampling.LANCZOS)
                bild = _bild_mit_abgerundeten_ecken(bild, radius=11)
                bild_tk = ImageTk.PhotoImage(bild)
        except (OSError, ValueError):
            continue

        thumbnail_refs.append(bild_tk)
        zelle = tk.Frame(thumbnail_inhalt, bg="#FFFFFF", relief="flat",
                         highlightthickness=1, highlightbackground="#D8E2F4")
        zelle.grid(row=index // spalten, column=index % spalten, padx=8, pady=8, sticky="n")

        bild_label = tk.Label(zelle, image=bild_tk, bg="#FFFFFF", bd=0)
        bild_label.pack(padx=6, pady=(6, 3))
        name_label = tk.Label(
            zelle, text=datei.name, wraplength=132, font=("DejaVu Sans", 8),
            bg="#FFFFFF", fg="#263858"
        )
        name_label.pack(padx=5, pady=(0, 7))

        for widget in (zelle, bild_label, name_label):
            widget.bind(
                "<ButtonRelease-3>",
                lambda event, pfad=datei: einzelbild_kontextmenue(event, pfad),
            )
            _thumbnail_hover_binden(widget, datei)

    thumbnail_index = ende
    thumbnail_inhalt.update_idletasks()
    thumbnail_canvas.configure(scrollregion=thumbnail_canvas.bbox("all"))
    if thumbnail_index < len(thumbnail_dateien):
        thumbnail_job = fenster.after(1, _thumbnails_naechster_batch)
    else:
        thumbnail_job = None



AKTIVES_KONTEXTMENUE = None
_KONTEXTMENUE_BINDUNGEN = []


def _kontextmenue_schliessen(event=None):
    global AKTIVES_KONTEXTMENUE, _KONTEXTMENUE_BINDUNGEN
    menue = AKTIVES_KONTEXTMENUE
    if menue is None:
        return
    AKTIVES_KONTEXTMENUE = None

    for sequenz, funcid in _KONTEXTMENUE_BINDUNGEN:
        try:
            fenster.unbind_class("all", sequenz, funcid)
        except Exception:
            pass
    _KONTEXTMENUE_BINDUNGEN = []

    try:
        menue.unpost()
    except tk.TclError:
        pass
    try:
        menue.destroy()
    except tk.TclError:
        pass


def _kontextmenue_aussenklick(event):
    menue = AKTIVES_KONTEXTMENUE
    if menue is None:
        return
    widget_pfad = str(event.widget)
    menue_pfad = str(menue)
    if widget_pfad == menue_pfad or widget_pfad.startswith(menue_pfad + "."):
        return
    _kontextmenue_schliessen()


def _kontextmenue_fokusverlust(_event=None):
    if AKTIVES_KONTEXTMENUE is not None:
        _kontextmenue_schliessen()


def einzelbild_kontextmenue(event, datei):
    global AKTIVES_KONTEXTMENUE, _KONTEXTMENUE_BINDUNGEN
    if ANALYSE_LAEUFT:
        return
    _kontextmenue_schliessen()

    menue = tk.Menu(fenster, tearoff=0)
    AKTIVES_KONTEXTMENUE = menue
    menue.add_command(
        label="Dieses Bild analysieren",
        command=lambda pfad=datei: einzelbild_analyse_starten(pfad),
    )

    for sequenz in ("<ButtonPress-1>", "<ButtonPress-2>", "<ButtonPress-3>"):
        funcid = fenster.bind_class("all", sequenz, _kontextmenue_aussenklick, add="+")
        _KONTEXTMENUE_BINDUNGEN.append((sequenz, funcid))
    menue.bind("<Escape>", _kontextmenue_schliessen, add="+")

    try:
        menue.tk_popup(event.x_root, event.y_root)
    except tk.TclError:
        _kontextmenue_schliessen()


def einzelbild_analyse_starten(datei):
    global ANALYSE_LAEUFT
    if ANALYSE_LAEUFT:
        return

    ANALYSE_LAEUFT = True
    STOP["abbrechen"] = False
    status_bild.config(text=f"Einzelbildanalyse: {datei.name}")
    restzeit_label.config(text="")
    fenster.update_idletasks()

    try:
        ergebnis = einzelbild_analysieren(datei, fenster, STOP)
        status = ergebnis["status"]

        if status == "kein_gesicht":
            messagebox.showinfo(
                "Keine Gesichter",
                "In diesem Bild wurden keine Gesichter erkannt.",
                parent=fenster,
            )
        elif status == "kein_gesicht_groessengrenze":
            messagebox.showinfo(
                "Keine ausreichend großen Gesichter",
                "Die erkannten Gesichter unterschreiten die eingestellte Mindestgröße.",
                parent=fenster,
            )
        elif status == "nicht_lesbar":
            messagebox.showerror(
                "Bild nicht lesbar",
                "Das ausgewählte Bild konnte nicht geöffnet werden.",
                parent=fenster,
            )
        elif status == "datei_fehlt":
            messagebox.showerror(
                "Datei nicht gefunden",
                "Das ausgewählte Bild ist nicht mehr vorhanden.",
                parent=fenster,
            )
        elif status == "ok":
            status_bild.config(
                text=f"Einzelbildanalyse beendet: {ergebnis['zugeordnet']} von "
                     f"{ergebnis['gesichter']} Gesichtern zugeordnet"
            )
        elif status == "verworfen":
            status_bild.config(text="Bild verworfen")
        elif status == "gestoppt":
            status_bild.config(text="Einzelbildanalyse abgebrochen")
    except Exception as exc:
        messagebox.showerror(
            "Fehler bei der Einzelbildanalyse",
            str(exc),
            parent=fenster,
        )
    finally:
        ANALYSE_LAEUFT = False
        STOP["abbrechen"] = False
        try:
            fenster.update_idletasks()
        except tk.TclError:
            pass


def thumbnails_ausblenden():
    thumbnail_canvas.grid_remove()
    thumbnail_scrollbar.grid_remove()
    karussell.canvas.grid()



# Zentrale NeuraPix-Anzeige während des Analyseanlaufs.
_analyse_splash_job = None
_analyse_splash_frame = None
_analyse_splash_photo = None

def _analyse_splash_anzeigen():
    global _analyse_splash_frame, _analyse_splash_photo
    _analyse_splash_entfernen()
    _analyse_splash_frame = tk.Frame(karussell_frame, bg="#F4F7FD",
                                     highlightthickness=1, highlightbackground="#D8E2F4")
    _analyse_splash_frame.place(relx=0.5, rely=0.5, anchor="center")
    try:
        logo = Image.open(BRANDING_DIR / "neurapix_logo.png").convert("RGBA")
        logo.thumbnail((430, 118), Image.Resampling.LANCZOS)
        _analyse_splash_photo = ImageTk.PhotoImage(logo)
        tk.Label(_analyse_splash_frame, image=_analyse_splash_photo,
                 bg="#F4F7FD", bd=0).pack(padx=34, pady=(24, 12))
    except (OSError, ValueError):
        tk.Label(_analyse_splash_frame, text="NeuraPix",
                 font=("DejaVu Sans", 25, "bold"), fg="#17264A",
                 bg="#F4F7FD").pack(padx=34, pady=(30, 12))
    tk.Label(_analyse_splash_frame, text="Analyse wird gestartet …",
             font=("DejaVu Sans", 13), fg="#263858",
             bg="#F4F7FD").pack(pady=(0, 22), padx=34)

def _analyse_splash_pruefen():
    global _analyse_splash_job
    if not ANALYSE_LAEUFT or _analyse_splash_frame is None:
        _analyse_splash_job = None
        return
    try:
        if karussell.canvas.find_all():
            _analyse_splash_entfernen()
            return
        _analyse_splash_job = fenster.after(180, _analyse_splash_pruefen)
    except tk.TclError:
        _analyse_splash_job = None

def _analyse_splash_entfernen():
    global _analyse_splash_frame, _analyse_splash_photo, _analyse_splash_job
    if _analyse_splash_job is not None:
        try:
            fenster.after_cancel(_analyse_splash_job)
        except tk.TclError:
            pass
        _analyse_splash_job = None
    if _analyse_splash_frame is not None:
        try:
            _analyse_splash_frame.destroy()
        except tk.TclError:
            pass
        _analyse_splash_frame = None
    _analyse_splash_photo = None


def analyse_starten():
    global ANALYSE_LAEUFT
    if not analyse_ordner:
        messagebox.showwarning(
            "Keine Analyseordner",
            "Bitte zuerst über Datei → Analyseordner hinzufügen einen Bildordner wählen.",
            parent=fenster,
        )
        return

    bilder = alle_analysebilder()
    if not bilder:
        messagebox.showinfo(
            "Keine Bilder",
            "In den ausgewählten Analyseordnern wurden keine Bilder gefunden.",
            parent=fenster,
        )
        return

    STOP["abbrechen"] = False
    ANALYSE_LAEUFT = True
    thumbnails_ausblenden()
    karussell.rahmen_entfernen()
    _analyse_splash_anzeigen()
    fortschritt["maximum"] = len(bilder)
    fortschritt["value"] = 0

    ordner_info.grid_remove()
    fortschritt_frame.grid()
    status_bild.config(text="Analyse wird gestartet …")
    restzeit_label.config(text="")
    namens_frame.grid_remove()
    ergebnis_label.grid_remove()
    button_frame.grid_remove()
    karussell_frame.grid()
    karussell.canvas.grid()
    fenster.title("NeuraPix – Analyse läuft")
    fenster.bind("<Escape>", lambda _event: analyse_stoppen())

    # Erst den aktuellen GUI-Zustand zeichnen lassen, dann die Analyse starten.
    fenster.update_idletasks()
    fenster.after(180, _analyse_splash_pruefen)
    fenster.after(100, lambda: analyse_ausfuehren(list(analyse_ordner)))


def analyse_ausfuehren(ordner):
    global ANALYSE_LAEUFT
    try:
        bilder_analysieren(
            ordner,
            fortschritt,
            status_bild,
            restzeit_label,
            karussell,
            ergebnis_label,
            STOP,
            fenster,
            namens_frame,
            hintergrund_status=lambda: fenster.state() in ("iconic", "withdrawn"),
        )
    finally:
        _analyse_splash_entfernen()
        ANALYSE_LAEUFT = False
        fenster.unbind("<Escape>")
        if not SCHLIESSEN_ANGEFORDERT:
            karussell.rahmen_entfernen()
            fenster.title("NeuraPix")
            ordner_info.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
            fortschritt_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
            if EINSTELLUNGEN["STATUSLEISTE_AKTIV"]:
                ergebnis_label.grid(row=4, column=0, sticky="ew", padx=10, pady=3)
            button_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=(4, 10))
            analyse_button.grid()
            stop_button.grid_remove()
            status_bild.config(text="Analyse beendet")
            if analyse_ordner:
                zeige_thumbnails(alle_analysebilder())
        else:
            tray_beenden()
            try:
                fenster.destroy()
            except tk.TclError:
                pass


def analyse_stoppen():
    STOP["abbrechen"] = True


def tray_beenden():
    global TRAY_ICON, TRAY_THREAD, TRAY_LOOP
    loop = TRAY_LOOP
    thread = TRAY_THREAD
    TRAY_ICON = None
    TRAY_LOOP = None
    if loop is not None and GLib is not None:
        try:
            GLib.idle_add(loop.quit)
        except Exception as exc:
            print(f"GTK-Tray konnte nicht beendet werden: {exc}")
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=2.0)
    TRAY_THREAD = None


def fenster_anzeigen():
    try:
        fenster.deiconify()
        fenster.state("normal")
        fenster.lift()
        fenster.focus_force()
    except tk.TclError:
        pass


def tray_aktion_anzeigen(*_args):
    try:
        fenster.after(0, fenster_anzeigen)
    except tk.TclError:
        pass


def tray_aktion_bilder_ansehen(*_args):
    """Fenster aus dem Tray holen und direkt die Bilderansicht öffnen."""
    def oeffnen():
        fenster_anzeigen()
        if bilderansicht_frame is None:
            bilder_ansehen()
        else:
            fenster.title("NeuraPix – Bilder ansehen")

    try:
        fenster.after(0, oeffnen)
    except tk.TclError:
        pass


def tray_aktion_beenden(*_args):
    try:
        fenster.after(0, beenden)
    except tk.TclError:
        pass


def _gtk_tray_worker():
    global TRAY_ICON, TRAY_LOOP, TRAY_START_RESULT
    try:
        Gtk.init([])
        # Eigenes NeuraPix-Logo statt des bisherigen Kamera-Symbols verwenden.
        if APP_ICON.is_file():
            icon = Gtk.StatusIcon.new_from_file(str(APP_ICON.resolve()))
        else:
            icon = Gtk.StatusIcon.new_from_icon_name("image-x-generic")
        icon.set_title("NeuraPix")
        icon.set_tooltip_text("NeuraPix – läuft im Hintergrund")
        icon.set_visible(True)

        menu = Gtk.Menu()
        for titel, callback in (
            ("Hauptfenster starten", tray_aktion_anzeigen),
            ("Bilder ansehen", tray_aktion_bilder_ansehen),
            ("Programm beenden", tray_aktion_beenden),
        ):
            item = Gtk.MenuItem(label=titel)
            item.connect("activate", callback)
            menu.append(item)
        menu.show_all()

        icon.connect("activate", tray_aktion_anzeigen)

        def popup_menu(_icon, button, activate_time):
            menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, activate_time)

        icon.connect("popup-menu", popup_menu)

        loop = GLib.MainLoop()
        TRAY_ICON = icon
        TRAY_LOOP = loop
        TRAY_START_RESULT = True
        if TRAY_START_EVENT is not None:
            TRAY_START_EVENT.set()
        loop.run()
        icon.set_visible(False)
    except Exception as exc:
        TRAY_START_RESULT = False
        print(f"GTK-System-Tray konnte nicht gestartet werden: {exc}")
        if TRAY_START_EVENT is not None:
            TRAY_START_EVENT.set()
    finally:
        TRAY_ICON = None
        TRAY_LOOP = None


def tray_starten():
    global TRAY_THREAD, TRAY_START_EVENT, TRAY_START_RESULT
    if Gtk is None or GLib is None:
        print("GTK-Tray nicht verfügbar. Installiere: sudo apt install python3-gi gir1.2-gtk-3.0")
        return False
    if TRAY_THREAD is not None and TRAY_THREAD.is_alive() and TRAY_ICON is not None:
        return True
    TRAY_START_EVENT = threading.Event()
    TRAY_START_RESULT = False
    TRAY_THREAD = threading.Thread(
        target=_gtk_tray_worker,
        name="FotoKI-GTK-Tray",
        daemon=True,
    )
    TRAY_THREAD.start()
    if not TRAY_START_EVENT.wait(timeout=4.0) or not TRAY_START_RESULT:
        print("GTK-Tray konnte nicht initialisiert werden.")
        return False
    return True


def fenster_schliessen():
    if not EINSTELLUNGEN.get("SCHLIESSEN_IN_TRAY", True):
        beenden()
        return

    if not tray_starten():
        messagebox.showerror(
            "System-Tray nicht verfügbar",
            "Der GTK-System-Tray ist nicht verfügbar.\n\n"
            "Installiere die Systempakete mit:\n"
            "sudo apt install python3-gi gir1.2-gtk-3.0\n\n"
            "Das Fenster bleibt geöffnet.",
            parent=fenster,
        )
        return
    fenster.withdraw()


def beenden():
    global SCHLIESSEN_ANGEFORDERT
    STOP["abbrechen"] = True
    if ANALYSE_LAEUFT:
        SCHLIESSEN_ANGEFORDERT = True
        fenster.title("NeuraPix – wird beendet ...")
        return
    tray_beenden()
    try:
        fenster.quit()
        fenster.destroy()
    except tk.TclError:
        pass


def warteschlange_aktualisieren():
    try:
        anzahl = warteschlange_anzahl()
        if WARTESCHLANGE_ANSICHT:
            warteschlange_button.config(
                text="Zurück zur normalen Ansicht",
                state="normal",
            )
        else:
            warteschlange_button.config(
                text=f"Unbekannte Gesichter zur Zuordnung: {anzahl}",
                state="normal" if anzahl else "disabled",
            )
    except (tk.TclError, OSError):
        pass


def warteschlange_ansicht_oeffnen():
    global WARTESCHLANGE_ANSICHT
    if ANALYSE_LAEUFT:
        return
    eintraege = lade_warteschlange()
    if not eintraege:
        warteschlange_aktualisieren()
        return

    dateien = []
    gesehen = set()
    for eintrag in eintraege:
        pfad = Path(eintrag.get("datei", ""))
        schluessel = str(pfad)
        if pfad.is_file() and schluessel not in gesehen:
            dateien.append(pfad)
            gesehen.add(schluessel)

    WARTESCHLANGE_ANSICHT = True
    fenster_anzeigen()
    namens_frame.grid_remove()
    karussell.canvas.grid_remove()
    ordner_info.config(
        text=f"Warteschlange: {len(eintraege)} Gesichter in {len(dateien)} Bildern"
    )
    analyse_button.config(
        text="Warteschlange analysieren",
        command=warteschlange_ansicht_oeffnen,
        state="normal" if eintraege else "disabled",
    )
    warteschlange_button.config(
        text="Zurück zur normalen Ansicht",
        command=warteschlange_ansicht_schliessen,
        state="normal",
    )
    zeige_thumbnails(dateien)
    fenster.title("NeuraPix – Warteschlange")


def warteschlange_ansicht_schliessen():
    global WARTESCHLANGE_ANSICHT
    WARTESCHLANGE_ANSICHT = False
    analyse_button.config(
        text="Bilder analysieren",
        command=analyse_starten,
        state="normal" if analyse_ordner and alle_analysebilder() else "disabled",
    )
    warteschlange_button.config(command=warteschlange_ansicht_oeffnen)
    if analyse_ordner:
        bilder = analyseordner_info_aktualisieren()
        zeige_thumbnails(bilder)
    else:
        zeige_thumbnails([])
    fenster.title("NeuraPix")


def warteschlange_bearbeiten_gui():
    global ANALYSE_LAEUFT
    if ANALYSE_LAEUFT:
        fenster_anzeigen()
        messagebox.showinfo(
            "Analyse läuft",
            "Die Warteschlange kann nach Abschluss der laufenden Analyse bearbeitet werden.",
            parent=fenster,
        )
        return
    if warteschlange_anzahl() == 0:
        warteschlange_aktualisieren()
        return

    fenster_anzeigen()
    ANALYSE_LAEUFT = True
    STOP["abbrechen"] = False
    analyse_button.config(state="disabled")
    warteschlange_button.config(state="disabled")
    try:
        erledigt, uebrig = warteschlange_bearbeiten(fenster, namens_frame, STOP)
        status_bild.config(
            text=f"Warteschlange bearbeitet: {erledigt}, noch offen: {uebrig}"
        )
    except Exception as exc:
        messagebox.showerror("Warteschlange", str(exc), parent=fenster)
    finally:
        ANALYSE_LAEUFT = False
        STOP["abbrechen"] = False
        if WARTESCHLANGE_ANSICHT:
            eintraege = lade_warteschlange()
            dateien = []
            gesehen = set()
            for eintrag in eintraege:
                pfad = Path(eintrag.get("datei", ""))
                if pfad.is_file() and str(pfad) not in gesehen:
                    dateien.append(pfad)
                    gesehen.add(str(pfad))
            ordner_info.config(
                text=f"Warteschlange: {len(eintraege)} Gesichter in {len(dateien)} Bildern"
            )
            zeige_thumbnails(dateien)
            analyse_button.config(state="normal" if eintraege else "disabled")
            warteschlange_button.config(state="normal")
        else:
            analyse_button.config(state="normal")
            warteschlange_aktualisieren()



def warteschlange_poll():
    warteschlange_aktualisieren()
    try:
        fenster.after(1000, warteschlange_poll)
    except tk.TclError:
        pass


bilderansicht_frame = None


def bilderansicht_schliessen(frame):
    global bilderansicht_frame

    # Sowohl den inneren Ansichtsrahmen als auch den äußeren Container entfernen.
    # Sonst bleibt ein leerer Frame über dem Karussell/den Thumbnails liegen.
    if bilderansicht_frame is not None:
        bilderansicht_frame.destroy()
        bilderansicht_frame = None
    else:
        frame.destroy()

    ordner_info.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
    karussell_frame.grid(row=1, column=0, sticky="nsew")
    fortschritt_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
    button_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=(4, 10))

    if EINSTELLUNGEN["STATUSLEISTE_AKTIV"]:
        ergebnis_label.grid(row=4, column=0, sticky="ew", padx=10, pady=3)
    else:
        ergebnis_label.grid_remove()

    # Den vorherigen Ordnerzustand wiederherstellen: Thumbnails anzeigen
    # und die Analyse-Schaltfläche passend zum Inhalt aktivieren.
    if analyse_ordner:
        bilder = analyseordner_info_aktualisieren()
        zeige_thumbnails(bilder)
    else:
        thumbnail_canvas.grid_remove()
        thumbnail_scrollbar.grid_remove()
        karussell.canvas.grid()

    fenster.title("NeuraPix")
    fenster.after_idle(lambda: zentriere_fenster(0.85))


def bilder_ansehen():
    global bilderansicht_frame
    if bilderansicht_frame is not None:
        return

    from suche import bilderansicht_erstellen

    # Die normale Arbeitsoberfläche ausblenden, Menüleiste bleibt am Hauptfenster.
    ordner_info.grid_remove()
    karussell_frame.grid_remove()
    fortschritt_frame.grid_remove()
    namens_frame.grid_remove()
    ergebnis_label.grid_remove()
    button_frame.grid_remove()

    bilderansicht_frame = tk.Frame(fenster)
    bilderansicht_frame.grid(row=1, column=0, sticky="nsew")
    fenster.title("NeuraPix – Bilder ansehen")

    try:
        bilderansicht_erstellen(
            bilderansicht_frame,
            bilderansicht_schliessen,
        )
    except Exception:
        bilderansicht_frame.destroy()
        bilderansicht_frame = None
        ordner_info.grid()
        karussell_frame.grid()
        fortschritt_frame.grid()
        button_frame.grid()
        if EINSTELLUNGEN["STATUSLEISTE_AKTIV"]:
            ergebnis_label.grid()
        fenster.title("NeuraPix")
        raise


def dateiformate_waehlen(parent):
    dialog = tk.Toplevel(parent)
    dialog.title("Dateiformate wählen")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.resizable(False, False)
    tk.Label(dialog, text="Zu durchsuchende Dateiformate", font=("Arial", 11, "bold")).pack(
        anchor="w", padx=14, pady=(14, 8)
    )
    variablen = {}
    for name, endungen in BILDFORMATE.items():
        var = tk.BooleanVar(value=bool(EINSTELLUNGEN["BILDFORMATE"].get(name, name in ("JPG", "JPEG"))))
        variablen[name] = var
        tk.Checkbutton(dialog, text=f"{name}  ({', '.join(endungen)})", variable=var).pack(anchor="w", padx=18)

    def speichern():
        auswahl = {name: var.get() for name, var in variablen.items()}
        if not any(auswahl.values()):
            messagebox.showwarning("Keine Formate", "Bitte mindestens ein Dateiformat auswählen.", parent=dialog)
            return
        EINSTELLUNGEN["BILDFORMATE"] = auswahl
        speichere_einstellungen(EINSTELLUNGEN)
        dialog.destroy()

    buttons = tk.Frame(dialog)
    buttons.pack(fill="x", padx=14, pady=14)
    tk.Button(buttons, text="Abbrechen", command=dialog.destroy).pack(side="right", padx=(6, 0))
    tk.Button(buttons, text="Speichern", command=speichern).pack(side="right")


def einstellungen_oeffnen():
    dialog = tk.Toplevel(fenster)
    dialog.title("Einstellungen")
    dialog.geometry("500x550")
    dialog.minsize(460, 510)
    dialog.transient(fenster)
    dialog.grab_set()
    dialog.columnconfigure(0, weight=1)

    tk.Label(dialog, text="Programmdateien", font=("Arial", 11, "bold")).grid(
        row=0, column=0, sticky="w", padx=14, pady=(14, 4)
    )
    pfad_label = tk.Label(
        dialog, text=str(ordner_programmdateien()), anchor="w", wraplength=420
    )
    pfad_label.grid(row=1, column=0, sticky="ew", padx=14)

    def ablageort_aendern():
        programmdateien_ablageort_waehlen()
        pfad_label.config(text=str(ordner_programmdateien()))

    tk.Button(
        dialog, text="Ort für Programmdateien wählen...", command=ablageort_aendern
    ).grid(row=2, column=0, sticky="w", padx=14, pady=(5, 10))

    tk.Label(
        dialog,
        text="Verarbeite nur Gesichter, die mindestens",
        font=("Arial", 11, "bold"),
    ).grid(row=3, column=0, sticky="w", padx=14, pady=(2, 4))
    gesichtsgroesse_prozent = tk.StringVar(
        value=str(EINSTELLUNGEN.get("MIN_GESICHTSGROESSE_PROZENT", 0)).rstrip("0").rstrip(".")
        if isinstance(EINSTELLUNGEN.get("MIN_GESICHTSGROESSE_PROZENT", 0), float)
        else str(EINSTELLUNGEN.get("MIN_GESICHTSGROESSE_PROZENT", 0))
    )
    groesse_frame = tk.Frame(dialog)
    groesse_frame.grid(row=4, column=0, sticky="w", padx=14)
    tk.Entry(groesse_frame, textvariable=gesichtsgroesse_prozent, width=7).pack(side="left")
    tk.Label(
        groesse_frame,
        text="% so breit sind wie das größte Gesicht des Bildes (0 = alle Gesichter)",
    ).pack(side="left", padx=(5, 0))

    tk.Label(dialog, text="Countdown bis Skip (Sekunden)").grid(
        row=5, column=0, sticky="w", padx=14, pady=(10, 2)
    )
    countdown = tk.StringVar(value=str(EINSTELLUNGEN["COUNTDOWN_SEKUNDEN"]))
    tk.Entry(dialog, textvariable=countdown, width=8).grid(
        row=6, column=0, sticky="w", padx=14
    )

    statusleiste = tk.BooleanVar(value=EINSTELLUNGEN["STATUSLEISTE_AKTIV"])
    tk.Checkbutton(
        dialog, text="Statusanzeige während der Analyse anzeigen", variable=statusleiste
    ).grid(row=7, column=0, sticky="w", padx=14, pady=(10, 0))

    karussell_aktiv = tk.BooleanVar(value=EINSTELLUNGEN["KARUSSELL_AKTIV"])
    tk.Checkbutton(
        dialog, text="Animiertes Bilderkarussell aktivieren", variable=karussell_aktiv
    ).grid(row=8, column=0, sticky="w", padx=14)

    mouseover_aktiv = tk.BooleanVar(
        value=EINSTELLUNGEN.get("MOUSEOVER_AKTIV", True)
    )
    mouseover_frame = tk.Frame(dialog)
    mouseover_frame.grid(row=9, column=0, sticky="w", padx=14, pady=(10, 0))
    tk.Checkbutton(
        mouseover_frame,
        text="Größere Darstellung bei Mouse over nach",
        variable=mouseover_aktiv,
    ).pack(side="left")

    mouseover_verzoegerung = tk.StringVar(
        value=str(EINSTELLUNGEN.get("MOUSEOVER_VERZOEGERUNG_MS", 100))
    )

    def nur_ziffern(neuer_wert):
        return neuer_wert == "" or neuer_wert.isdigit()

    pruef_befehl = (dialog.register(nur_ziffern), "%P")
    mouseover_eingabe = tk.Entry(
        mouseover_frame,
        textvariable=mouseover_verzoegerung,
        width=6,
        validate="key",
        validatecommand=pruef_befehl,
    )
    mouseover_eingabe.pack(side="left", padx=(4, 3))
    tk.Label(mouseover_frame, text="Millisekunden").pack(side="left")

    def mouseover_status_aktualisieren(*_):
        mouseover_eingabe.config(
            state="normal" if mouseover_aktiv.get() else "disabled"
        )

    mouseover_aktiv.trace_add("write", mouseover_status_aktualisieren)
    mouseover_status_aktualisieren()

    tk.Label(dialog, text="Erkennungsschwelle", font=("Arial", 11, "bold")).grid(
        row=10, column=0, sticky="w", padx=14, pady=(12, 2)
    )
    schwelle_frame = tk.Frame(dialog)
    schwelle_frame.grid(row=11, column=0, sticky="ew", padx=14)
    schwelle_frame.columnconfigure(0, weight=1)

    # StringVar vermeiden: DoubleVar kann unter deutscher Locale
    # Dezimalwerte mit Komma liefern, die Tcl getdouble() nicht akzeptiert.
    schwelle_wert = tk.StringVar(
        value=f"{float(EINSTELLUNGEN.get('ERKENNUNGSSCHWELLE', 1.2)):.2f}"
    )
    schwelle_anzeige = tk.Label(
        schwelle_frame, text=f"{float(schwelle_wert.get().replace(',', '.')):.2f}", width=5, anchor="e"
    )
    schwelle_anzeige.grid(row=0, column=1, padx=(8, 0))

    def schwelle_aendern(wert):
        gerundet = round(float(str(wert).replace(",", ".")) / 0.05) * 0.05
        schwelle_wert.set(f"{gerundet:.2f}")
        schwelle_anzeige.config(text=f"{gerundet:.2f}")

    tk.Scale(
        schwelle_frame, from_=0.5, to=1.8, resolution=0.05,
        orient="horizontal", variable=schwelle_wert,
        command=schwelle_aendern, showvalue=False, length=300,
    ).grid(row=0, column=0, sticky="ew")

    tk.Button(dialog, text="Dateiformate wählen...", command=lambda: dateiformate_waehlen(dialog)).grid(
        row=12, column=0, sticky="w", padx=14, pady=(10, 0)
    )

    schliessen_in_tray = tk.BooleanVar(
        value=EINSTELLUNGEN.get("SCHLIESSEN_IN_TRAY", True)
    )
    tk.Checkbutton(
        dialog,
        text="Schließen über [X] schiebt in Tray",
        variable=schliessen_in_tray,
    ).grid(row=13, column=0, sticky="w", padx=14, pady=(10, 0))

    def speichern():
        try:
            wert = int(countdown.get())
            if wert < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Fehler", "Bitte eine positive ganze Zahl für den Countdown eingeben.", parent=dialog)
            return

        EINSTELLUNGEN["COUNTDOWN_SEKUNDEN"] = wert
        try:
            mindest_prozent = float(
                str(gesichtsgroesse_prozent.get()).replace(",", ".")
            )
            if not 0 <= mindest_prozent <= 100:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Fehler",
                "Bitte einen Prozentwert zwischen 0 und 100 eingeben.",
                parent=dialog,
            )
            return
        EINSTELLUNGEN["MIN_GESICHTSGROESSE_PROZENT"] = mindest_prozent
        EINSTELLUNGEN["STATUSLEISTE_AKTIV"] = statusleiste.get()
        EINSTELLUNGEN["KARUSSELL_AKTIV"] = karussell_aktiv.get()
        try:
            mouseover_ms = int(mouseover_verzoegerung.get())
            if mouseover_ms < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Fehler",
                "Bitte eine nichtnegative ganze Zahl für die Mouseover-Verzögerung eingeben.",
                parent=dialog,
            )
            return

        EINSTELLUNGEN["MOUSEOVER_AKTIV"] = mouseover_aktiv.get()
        EINSTELLUNGEN["MOUSEOVER_VERZOEGERUNG_MS"] = mouseover_ms
        EINSTELLUNGEN["ERKENNUNGSSCHWELLE"] = round(
            float(str(schwelle_wert.get()).replace(",", ".")), 2
        )
        EINSTELLUNGEN["SCHLIESSEN_IN_TRAY"] = schliessen_in_tray.get()
        speichere_einstellungen(EINSTELLUNGEN)
        karussell.set_aktiv(EINSTELLUNGEN["KARUSSELL_AKTIV"])
        if EINSTELLUNGEN["STATUSLEISTE_AKTIV"]:
            ergebnis_label.grid()
        else:
            ergebnis_label.grid_remove()
        dialog.destroy()

    button_frame = tk.Frame(dialog)
    button_frame.grid(row=14, column=0, sticky="e", padx=14, pady=14)
    tk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side="right", padx=(6, 0))
    tk.Button(button_frame, text="Speichern", command=speichern).pack(side="right")




def datenbank_backup():
    try:
        ziel = erstelle_backup("manuell")
        if ziel is None:
            messagebox.showinfo("Backup", "Es sind noch keine Datenbankdateien vorhanden.", parent=fenster)
        else:
            messagebox.showinfo("Backup erstellt", f"Sicherung gespeichert unter:\n{ziel}", parent=fenster)
    except Exception as exc:
        messagebox.showerror("Backup fehlgeschlagen", str(exc), parent=fenster)


def datenbank_pruefen():
    try:
        bericht = pruefe_datenbank()
        zeilen = [
            f"Personen: {bericht['personen']}",
            f"Gesichtsdatensätze: {bericht['gesichter']}",
            f"Nicht erreichbare Bildpfade: {bericht['fehlende_bilder']}",
            "",
            "Dateien:",
            *(bericht["dateien"] or ["Keine Datenbankdateien gefunden."]),
            "",
            "Fehler:",
            *(bericht["fehler"] or ["Keine strukturellen Fehler gefunden."]),
            "",
            "Hinweise:",
            *(bericht["warnungen"] or ["Keine weiteren Hinweise."]),
        ]
        messagebox.showinfo("Datenbankprüfung", "\n".join(zeilen), parent=fenster)
    except Exception as exc:
        messagebox.showerror("Prüfung fehlgeschlagen", str(exc), parent=fenster)


def _duplikat_bild_vergroessern(datei):
    """Öffnet ein Duplikat in einer eigenen, größenangepassten Ansicht."""
    datei = Path(datei)
    try:
        with Image.open(datei) as original:
            bild = original.convert("RGB")
    except (OSError, ValueError) as exc:
        messagebox.showerror("Bild kann nicht geöffnet werden", str(exc), parent=fenster)
        return

    dialog = tk.Toplevel(fenster)
    dialog.title(f"Duplikat – {datei.name}")
    dialog.geometry("1000x760")
    dialog.transient(fenster)

    bild.thumbnail((960, 660), Image.Resampling.LANCZOS)
    bild_tk = ImageTk.PhotoImage(bild)
    label = tk.Label(dialog, image=bild_tk, background="black")
    label.image = bild_tk
    label.pack(fill="both", expand=True, padx=8, pady=8)

    tk.Label(
        dialog, text=str(datei), anchor="w", justify="left", wraplength=960
    ).pack(fill="x", padx=10, pady=(0, 8))
    tk.Button(dialog, text="Schließen", command=dialog.destroy).pack(pady=(0, 8))


def duplikate_anzeigen(gruppen, fehler, anzahl, ordner):
    """Zeigt Duplikatgruppen und erlaubt das Markieren sowie Verschieben in den Papierkorb."""
    dialog = tk.Toplevel(fenster)
    dialog.title("Gefundene Bildduplikate")
    dialog.geometry("1100x800")
    dialog.minsize(760, 520)
    dialog.transient(fenster)

    ausgewaehlt = {}
    bild_referenzen = []

    kopf = tk.Frame(dialog)
    kopf.pack(fill="x", padx=12, pady=10)
    tk.Label(
        kopf,
        text=f"Duplikatsuche abgeschlossen: {anzahl} geprüfte Bilder · "
             f"{len(gruppen)} Duplikatgruppen",
        font=("Arial", 12, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(kopf, text=f"Durchsuchter Ordner: {ordner}", anchor="w").pack(fill="x", pady=(3, 0))
    tk.Label(
        kopf,
        text="Bilder anklicken, um sie zu markieren. Erneuter Klick hebt die Markierung auf.",
        anchor="w",
    ).pack(fill="x", pady=(3, 0))

    status_label = tk.Label(kopf, text="0 Bilder markiert", anchor="w")
    status_label.pack(fill="x", pady=(5, 0))

    container = tk.Frame(dialog)
    container.pack(fill="both", expand=True, padx=10, pady=(0, 8))

    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    inhalt = tk.Frame(canvas)
    fenster_id = canvas.create_window((0, 0), window=inhalt, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    inhalt.bind(
        "<Configure>",
        lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.bind(
        "<Configure>",
        lambda event: canvas.itemconfigure(fenster_id, width=event.width),
    )

    def aktualisiere_auswahl():
        status_label.config(text=f"{len(ausgewaehlt)} Bilder markiert")
        for widgets in ausgewaehlt.values():
            karte = widgets["karte"]
            karte.config(
                background="#cfe8ff",
                highlightthickness=3,
                highlightbackground="#1674c8",
                highlightcolor="#1674c8",
            )
            for widget in widgets["labels"]:
                widget.config(background="#cfe8ff")

    def markierung_umschalten(datei):
        schluessel = str(datei)
        widgets = karten.get(schluessel)
        if widgets is None:
            return

        if schluessel in ausgewaehlt:
            del ausgewaehlt[schluessel]
            widgets["karte"].config(
                background=dialog.cget("background"),
                highlightthickness=0,
            )
            for widget in widgets["labels"]:
                widget.config(background=dialog.cget("background"))
        else:
            ausgewaehlt[schluessel] = widgets
            widgets["karte"].config(
                background="#cfe8ff",
                highlightthickness=3,
                highlightbackground="#1674c8",
                highlightcolor="#1674c8",
            )
            for widget in widgets["labels"]:
                widget.config(background="#cfe8ff")

        status_label.config(text=f"{len(ausgewaehlt)} Bilder markiert")

    def in_papierkorb_verschieben():
        if not ausgewaehlt:
            messagebox.showinfo(
                "Keine Auswahl", "Bitte zuerst mindestens ein Bild markieren.", parent=dialog
            )
            return

        anzahl_markiert = len(ausgewaehlt)
        bestaetigt = messagebox.askyesno(
            "Dateien in den Papierkorb verschieben?",
            f"Sollen die {anzahl_markiert} markierten Dateien wirklich "
            "in den Papierkorb verschoben werden?",
            parent=dialog,
        )
        if not bestaetigt:
            return

        try:
            from send2trash import send2trash
        except ImportError:
            messagebox.showerror(
                "Papierkorb nicht verfügbar",
                "Das Paket 'send2trash' ist nicht installiert. Es wurde nichts verschoben.",
                parent=dialog,
            )
            return

        verschoben = []
        fehler_verschieben = []

        for schluessel in list(ausgewaehlt):
            try:
                send2trash(schluessel)
                verschoben.append(schluessel)
            except Exception as exc:
                fehler_verschieben.append(f"{schluessel}: {exc}")

        for schluessel in verschoben:
            widgets = karten.pop(schluessel, None)
            ausgewaehlt.pop(schluessel, None)
            if widgets:
                widgets["karte"].destroy()

        aktualisiere_auswahl()
        canvas.configure(scrollregion=canvas.bbox("all"))

        if fehler_verschieben:
            details = "\\n".join(fehler_verschieben[:10])
            messagebox.showwarning(
                "Teilweise abgeschlossen",
                f"{len(verschoben)} Dateien wurden in den Papierkorb verschoben. "
                f"{len(fehler_verschieben)} Dateien konnten nicht verschoben werden.\\n\\n"
                f"{details}",
                parent=dialog,
            )
        else:
            messagebox.showinfo(
                "Abgeschlossen",
                f"{len(verschoben)} Dateien wurden in den Papierkorb verschoben.",
                parent=dialog,
            )

    karten = {}
    if not gruppen:
        tk.Label(
            inhalt,
            text="Keine identischen Bilder gefunden.",
            font=("Arial", 12),
            padx=20,
            pady=20,
        ).pack(anchor="w")
    else:
        for nummer, gruppe in enumerate(gruppen, 1):
            dateien = [Path(p) for p in gruppe["dateien"]]
            rahmen = tk.LabelFrame(
                inhalt,
                text=f"Duplikatgruppe {nummer} · {len(dateien)} Dateien",
                padx=8,
                pady=8,
            )
            rahmen.pack(fill="x", padx=5, pady=7)

            dateien_frame = tk.Frame(rahmen)
            dateien_frame.pack(fill="x")

            for spalte, datei in enumerate(dateien):
                karte = tk.Frame(
                    dateien_frame,
                    relief="groove",
                    borderwidth=1,
                    padx=6,
                    pady=6,
                    highlightthickness=0,
                )
                karte.grid(row=0, column=spalte, padx=6, pady=4, sticky="n")

                labels = []
                try:
                    with Image.open(datei) as original:
                        vorschau = original.convert("RGB")
                        vorschau.thumbnail((210, 155), Image.Resampling.LANCZOS)
                        bild_tk = ImageTk.PhotoImage(vorschau)
                    bild_referenzen.append(bild_tk)
                    bild_label = tk.Label(karte, image=bild_tk, cursor="hand2")
                    bild_label.pack(pady=(0, 5))
                    labels.append(bild_label)
                except (OSError, ValueError):
                    fehler_label = tk.Label(
                        karte, text="Vorschau nicht verfügbar", width=28, height=8,
                        cursor="hand2",
                    )
                    fehler_label.pack()
                    labels.append(fehler_label)

                name_label = tk.Label(
                    karte,
                    text=datei.name,
                    wraplength=210,
                    justify="center",
                    font=("Arial", 9, "bold"),
                    cursor="hand2",
                )
                name_label.pack(fill="x")
                labels.append(name_label)

                pfad_label = tk.Label(
                    karte,
                    text=str(datei),
                    wraplength=210,
                    justify="left",
                    font=("Arial", 8),
                    cursor="hand2",
                )
                pfad_label.pack(fill="x", pady=(3, 0))
                labels.append(pfad_label)

                widgets = {"karte": karte, "labels": labels}
                karten[str(datei)] = widgets

                karte.bind(
                    "<Button-1>",
                    lambda _event, pfad=datei: markierung_umschalten(pfad),
                )
                for widget in labels:
                    widget.bind(
                        "<Button-1>",
                        lambda _event, pfad=datei: markierung_umschalten(pfad),
                    )

    if fehler:
        fehler_frame = tk.LabelFrame(
            inhalt, text=f"Nicht lesbare Dateien: {len(fehler)}", padx=8, pady=6
        )
        fehler_frame.pack(fill="x", padx=5, pady=7)
        for fehler_datei in fehler[:50]:
            tk.Label(
                fehler_frame,
                text=str(fehler_datei),
                anchor="w",
                justify="left",
                wraplength=950,
            ).pack(fill="x")
        if len(fehler) > 50:
            tk.Label(
                fehler_frame, text=f"... und {len(fehler) - 50} weitere."
            ).pack(anchor="w")

    dialog._duplikat_bild_referenzen = bild_referenzen

    button_leiste = tk.Frame(dialog)
    button_leiste.pack(fill="x", padx=10, pady=(0, 10))
    tk.Button(
        button_leiste,
        text="Löschen",
        command=in_papierkorb_verschieben,
    ).pack(side="left")
    tk.Button(
        button_leiste,
        text="Schließen",
        command=dialog.destroy,
    ).pack(side="right")

def _duplikat_zeit_format(sekunden):
    if sekunden is None:
        return "wird berechnet …"
    sekunden = max(0, int(sekunden))
    minuten, sekunden = divmod(sekunden, 60)
    stunden, minuten = divmod(minuten, 60)
    if stunden:
        return f"{stunden}:{minuten:02d}:{sekunden:02d}"
    return f"{minuten}:{sekunden:02d}"


def datenbank_duplikate_suchen():
    ordner = filedialog.askdirectory(
        parent=fenster, title="Bildordner auf Duplikate prüfen"
    )
    if not ordner:
        return

    ereignisse = queue.Queue()
    fortschritt_dialog = tk.Toplevel(fenster)
    fortschritt_dialog.title("Duplikatsuche")
    fortschritt_dialog.geometry("520x190")
    fortschritt_dialog.resizable(False, False)
    fortschritt_dialog.transient(fenster)

    rahmen = tk.Frame(fortschritt_dialog, padx=18, pady=16)
    rahmen.pack(fill="both", expand=True)

    status = tk.Label(
        rahmen, text="Bilddateien werden gesucht …",
        anchor="w", justify="left", wraplength=480,
    )
    status.pack(fill="x", pady=(0, 10))

    balken = ttk.Progressbar(
        rahmen, orient="horizontal", mode="determinate", maximum=100
    )
    balken.pack(fill="x", pady=(0, 8))

    detail = tk.Label(rahmen, text="", anchor="w", justify="left")
    detail.pack(fill="x")

    zeit_label = tk.Label(rahmen, text="Restzeit: wird berechnet …", anchor="w")
    zeit_label.pack(fill="x", pady=(5, 0))

    ergebnis = {"daten": None, "fehler": None}

    def suche_im_hintergrund():
        try:
            daten = finde_dateiduplikate(
                ordner, fortschritt=lambda ereignis: ereignisse.put(ereignis)
            )
            ergebnis["daten"] = daten
        except Exception as exc:
            ergebnis["fehler"] = exc
        finally:
            ereignisse.put({"typ": "worker_fertig"})

    threading.Thread(target=suche_im_hintergrund, daemon=True).start()

    def status_pruefen():
        try:
            while True:
                ereignis = ereignisse.get_nowait()
                typ = ereignis.get("typ")

                if typ == "start":
                    anzahl = ereignis["anzahl"]
                    status.config(text=f"{anzahl:,} Fotos gefunden.".replace(",", "."))
                    if anzahl == 0:
                        balken["value"] = 100
                        detail.config(text="Keine unterstützten Bilddateien gefunden.")
                        zeit_label.config(text="Restzeit: 0 Sekunden")
                    else:
                        detail.config(text="Zeitmessung anhand der ersten zwei Bilder …")

                elif typ == "progress":
                    verarbeitet = ereignis["verarbeitet"]
                    anzahl = ereignis["anzahl"]
                    prozent = (verarbeitet / anzahl * 100) if anzahl else 100
                    balken["value"] = prozent
                    detail.config(
                        text=f"SHA-256: {verarbeitet:,} / {anzahl:,} Bilder geprüft "
                             f"({prozent:.1f} %)".replace(",", ".")
                    )
                    zeit_label.config(
                        text=f"Restzeit: {_duplikat_zeit_format(ereignis.get('rest_sekunden'))}"
                    )

                elif typ == "complete":
                    balken["value"] = 100
                    detail.config(
                        text=f"Fertig: {ereignis['verarbeitet']:,} Bilder geprüft."
                        .replace(",", ".")
                    )
                    zeit_label.config(
                        text=f"Gesamtdauer: {_duplikat_zeit_format(ereignis['dauer'])}"
                    )

                elif typ == "worker_fertig":
                    fortschritt_dialog.destroy()
                    if ergebnis["fehler"] is not None:
                        messagebox.showerror(
                            "Duplikatsuche fehlgeschlagen",
                            str(ergebnis["fehler"]),
                            parent=fenster,
                        )
                    elif ergebnis["daten"] is not None:
                        gruppen, fehler, anzahl = ergebnis["daten"]
                        duplikate_anzeigen(gruppen, fehler, anzahl, ordner)
                    return

        except queue.Empty:
            pass

        if fortschritt_dialog.winfo_exists():
            fenster.after(100, status_pruefen)

    fortschritt_dialog.protocol(
        "WM_DELETE_WINDOW",
        lambda: messagebox.showinfo(
            "Duplikatsuche läuft",
            "Die Suche läuft im Hintergrund und wird beim Schließen dieses Fensters nicht abgebrochen.",
            parent=fortschritt_dialog,
        ),
    )
    status_pruefen()


def datenbank_exportieren():
    ziel = filedialog.asksaveasfilename(
        parent=fenster, title="Datenbank exportieren",
        defaultextension=".zip", filetypes=[("NeuraPix-Datenbank", "*.zip")],
        initialfile=f"foto_ki_export_{datetime.now():%Y%m%d_%H%M%S}.zip",
    )
    if not ziel:
        return
    try:
        exportiere_datenbank(ziel)
        messagebox.showinfo("Export abgeschlossen", f"Datenbank exportiert:\n{ziel}", parent=fenster)
    except Exception as exc:
        messagebox.showerror("Export fehlgeschlagen", str(exc), parent=fenster)


def datenbank_wiederherstellen():
    quelle = filedialog.askopenfilename(
        parent=fenster, title="Datenbank-Backup auswählen",
        filetypes=[("NeuraPix-Datenbank", "*.zip")],
    )
    if not quelle:
        return
    if not messagebox.askyesno(
        "Datenbank ersetzen?",
        "Die aktuellen Daten werden durch den Inhalt des Backups ersetzt. "
        "Vorher wird automatisch eine Sicherung des aktuellen Standes erstellt.\n\nFortfahren?",
        parent=fenster,
    ):
        return
    try:
        backup, dateien = stelle_datenbank_wieder_her(quelle)
        messagebox.showinfo(
            "Wiederherstellung abgeschlossen",
            "Wiederhergestellt: " + ", ".join(dateien) +
            f"\n\nSicherung des vorherigen Standes:\n{backup}\n\nBitte NeuraPix neu starten.",
            parent=fenster,
        )
    except Exception as exc:
        messagebox.showerror("Wiederherstellung fehlgeschlagen", str(exc), parent=fenster)


def hilfe_oeffnen():
    """Öffnet eine strukturierte, thematisch gegliederte Programmh ilfe."""
    dialog = tk.Toplevel(fenster)
    dialog.title("NeuraPix – Benutzerhandbuch")
    _set_app_icon(dialog)
    dialog.geometry("900x680")
    dialog.minsize(760, 560)
    dialog.transient(fenster)

    haupt = tk.Frame(dialog, padx=20, pady=16)
    haupt.pack(fill="both", expand=True)

    tk.Label(
        haupt,
        text="NeuraPix",
        font=("Arial", 21, "bold"),
        anchor="w",
    ).pack(fill="x")

    tk.Label(
        haupt,
        text="Benutzerhandbuch · Funktionen, Arbeitsabläufe und Datenverwaltung",
        font=("Arial", 10),
        fg="#666666",
        anchor="w",
    ).pack(fill="x", pady=(2, 14))

    notebook = ttk.Notebook(haupt)
    notebook.pack(fill="both", expand=True)

    abschnitte = [
        (
            "Erste Schritte",
            [
                ("1. Analyseordner festlegen",
                 "Über Datei → Ordner wählen oder über den Ordnerhinweis in der Hauptansicht "
                 "öffnest du die Ordnerverwaltung. Dort kannst du mehrere Bildordner hinzufügen, "
                 "einzeln entfernen und die Auswahl übernehmen."),
                ("2. Bilder anzeigen",
                 "Nach der Auswahl werden unterstützte Bilddateien aus den Analyseordnern "
                 "eingelesen und als Vorschaubilder angezeigt. Welche Dateiformate berücksichtigt "
                 "werden, legst du unter Bearbeiten → Einstellungen fest."),
                ("3. Analyse starten",
                 "Mit „Bilder analysieren“ startest du die Gesichtserkennung für die ausgewählten "
                 "Bilder. Die Analyse kann je nach Bildmenge und Rechnerleistung einige Zeit dauern."),
                ("Bereits verarbeitete Bilder",
                 "Bilder, die bereits verarbeitet wurden, werden bei einem erneuten regulären "
                 "Analyselauf berücksichtigt und nicht unnötig erneut bearbeitet."),
            ],
        ),
        (
            "Gesichtserkennung",
            [
                ("Erkennung und Zuordnung",
                 "NeuraPix erkennt menschliche Gesichter und berechnet für jedes erkannte Gesicht "
                 "einen numerischen Gesichtsvektor. Dieser wird mit den bereits gespeicherten "
                 "Vektoren verglichen."),
                ("Unbekannte Personen benennen",
                 "Wird ein Gesicht keiner bekannten Person sicher zugeordnet, erscheint die "
                 "Namenseingabe. Gib den Namen ein und bestätige. Der Gesichtsvektor wird der "
                 "Person zugeordnet. Weitere ausreichend ähnliche Gesichter können anschließend "
                 "automatisch derselben Person zugeordnet werden."),
                ("Einzelbildanalyse",
                 "Über das Kontextmenü eines Bildes kannst du die Einzelbildanalyse starten. "
                 "Sie eignet sich, um ein bestimmtes Bild gezielt zu untersuchen oder eine "
                 "Personenzuordnung zu korrigieren."),
                ("Erkennungsschwelle",
                 "Die Erkennungsschwelle steuert, wie großzügig Gesichter vorhandenen Personen "
                 "zugeordnet werden. Ein höherer Wert lässt mehr Zuordnungen zu, erhöht aber das "
                 "Risiko falscher Treffer. Ein niedrigerer Wert ist strenger und kann dazu führen, "
                 "dass bekannte Personen häufiger erneut benannt werden müssen."),
            ],
        ),
        (
            "Warteschlange",
            [
                ("Wofür ist die Warteschlange?",
                 "Gesichter, die während einer Analyse nicht zugeordnet oder bewusst zurückgestellt "
                 "wurden, können in der Warteschlange gesammelt und später gezielt bearbeitet werden."),
                ("Warteschlange öffnen",
                 "Über die Warteschlangen-Schaltfläche wechselst du in eine Ansicht, die die "
                 "betroffenen Bilder als Vorschaubilder zeigt. Du kannst die Bilder dort gesammelt "
                 "durchsehen und bearbeiten."),
                ("Bearbeitung",
                 "Du kannst einzelne Bilder analysieren, Personen benennen oder Einträge "
                 "überspringen. Bereits gespeicherte Zuordnungen werden bei der weiteren Verarbeitung "
                 "berücksichtigt."),
            ],
        ),
        (
            "Duplikate finden",
            [
                ("Suche starten",
                 "Unter Datenbank → Bildduplikate suchen wählst du einen Ordner aus. NeuraPix "
                 "ermittelt zunächst die unterstützten Bilddateien und berechnet anschließend "
                 "für jede Datei einen SHA-256-Prüfwert."),
                ("Was gilt als Duplikat?",
                 "Dateien mit identischem SHA-256-Prüfwert sind bytegenau identisch. Umbenannte "
                 "Kopien werden deshalb ebenfalls gefunden. Ein erneut gespeichertes oder anders "
                 "komprimiertes Bild kann dagegen einen anderen Prüfwert besitzen und wird nicht "
                 "als identische Datei erkannt."),
                ("Fortschritt und Ergebnis",
                 "Während der Suche zeigt ein Fortschrittsfenster die Anzahl gefundener und bereits "
                 "geprüfter Bilder sowie eine dynamische Restzeitschätzung. Anschließend werden "
                 "Duplikatgruppen mit Vorschaubildern und Dateipfaden angezeigt."),
                ("Bilder markieren und entfernen",
                 "Klicke ein Bild an, um es zu markieren. Ein erneuter Klick hebt die Markierung "
                 "auf. Über „Löschen“ kannst du die markierten Dateien nach einer Sicherheitsabfrage "
                 "in den Papierkorb verschieben. Nicht markierte Dateien bleiben unverändert."),
                ("Großansicht",
                 "Ein Klick auf das Vorschaubild öffnet zusätzlich die vergrößerte Bildansicht."),
            ],
        ),
        (
            "Datenbank & Sicherung",
            [
                ("Backup jetzt erstellen",
                 "Erstellt eine Sicherung der lokalen Datenbankdateien im vorgesehenen Backup-Ordner. "
                 "Diese Sicherung dient dazu, einen früheren Datenstand wiederherzustellen."),
                ("Datenbank prüfen",
                 "Prüft die gespeicherten Datenbankdateien auf Lesbarkeit und strukturelle "
                 "Auffälligkeiten. Der Prüfbericht enthält unter anderem Personen, Gesichtsdatensätze "
                 "und nicht erreichbare Bildpfade."),
                ("Datenbank exportieren",
                 "Erstellt eine ZIP-Datei, die du an einem frei wählbaren Ort speichern und "
                 "beispielsweise auf einen anderen Rechner übertragen kannst."),
                ("Datenbank wiederherstellen",
                 "Lädt eine zuvor exportierte ZIP-Datei. Die aktuellen Daten werden ersetzt. "
                 "Vor der Wiederherstellung erstellt NeuraPix automatisch eine zusätzliche Sicherung "
                 "des bisherigen Datenstands."),
            ],
        ),
        (
            "Einstellungen & Programm",
            [
                ("Mindestgröße für Gesichter",
                 "Legt fest, welche Größenstufe bei der Gesichtserkennung mindestens berücksichtigt "
                 "wird. Eine größere Mindestgröße kann kleine Gesichter ausfiltern."),
                ("Countdown bis Skip",
                 "Bestimmt, wie viele Sekunden bis zum automatischen Überspringen eines "
                 "Namensdialogs vergehen."),
                ("Darstellung",
                 "Du kannst die Statusanzeige während der Analyse, das animierte Bilderkarussell "
                 "und die größere Mouseover-Vorschau aktivieren oder deaktivieren. Die Verzögerung "
                 "der Mouseover-Vorschau wird in Millisekunden angegeben."),
                ("Programmdateien",
                 "Über „Ort für Programmdateien wählen“ legst du fest, wo NeuraPix seine lokalen "
                 "Datenbank- und Einstellungsdateien ablegt."),
                ("Schließen über [X]",
                 "Wenn „Schließen über [X] schiebt in Tray“ aktiviert ist, wird das Fenster beim "
                 "Klick auf [X] in den System-Tray verschoben, statt das Programm vollständig zu beenden."),
                ("Änderungen speichern",
                 "Bestätige Änderungen im Einstellungsfenster mit „Speichern“. Mit „Abbrechen“ "
                 "werden die Änderungen dieses Dialogs verworfen."),
            ],
        ),
    ]

    for titel, inhalte in abschnitte:
        tab = tk.Frame(notebook, padx=18, pady=16)
        notebook.add(tab, text=titel)

        text_container = tk.Frame(tab)
        text_container.pack(fill="both", expand=True)

        hilfetext = tk.Text(
            text_container,
            wrap="word",
            padx=12,
            pady=10,
            relief="flat",
            borderwidth=0,
            font=("Arial", 10),
            spacing1=2,
            spacing3=7,
            cursor="arrow",
            takefocus=False,
        )
        scrollbar = ttk.Scrollbar(
            text_container, orient="vertical", command=hilfetext.yview
        )
        hilfetext.configure(yscrollcommand=scrollbar.set)

        hilfetext.tag_configure(
            "abschnitt",
            font=("Arial", 12, "bold"),
            foreground="#2457a7",
            spacing1=8,
            spacing3=3,
        )
        hilfetext.tag_configure(
            "beschreibung",
            font=("Arial", 10),
            lmargin1=4,
            lmargin2=4,
            spacing3=10,
        )

        for ueberschrift, beschreibung in inhalte:
            hilfetext.insert("end", ueberschrift + "\n", "abschnitt")
            hilfetext.insert("end", beschreibung + "\n\n", "beschreibung")

        hilfetext.config(state="disabled")
        hilfetext.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    fuss = tk.Frame(haupt)
    fuss.pack(fill="x", pady=(12, 0))

    tk.Label(
        fuss,
        text="Hinweis: Die Originalbilder werden durch die Analyse nicht verändert.",
        fg="#666666",
        font=("Arial", 9),
        anchor="w",
    ).pack(side="left", fill="x", expand=True)

    tk.Button(
        fuss,
        text="Schließen",
        width=12,
        command=dialog.destroy,
    ).pack(side="right")

    dialog.update_idletasks()
    dialog.wait_visibility()
    dialog.grab_set()


def info_oeffnen():
    dialog = tk.Toplevel(fenster)
    dialog.title("Info – NeuraPix")
    _set_app_icon(dialog)
    dialog.transient(fenster)
    dialog.resizable(False, False)
    rahmen = tk.Frame(dialog, padx=24, pady=20)
    rahmen.pack()
    tk.Label(rahmen, text="NeuraPix", font=("Arial", 20, "bold")).pack(pady=(0, 4))
    tk.Label(rahmen, text=f"Version {VERSION}", font=("Arial", 10, "bold")).pack(pady=(0, 14))
    tk.Label(
        rahmen,
        text=("NeuraPix unterstützt beim Verwalten und Wiederfinden von Fotos anhand "
              "erkannter menschlicher Gesichter. Das Programm erstellt Gesichtsvektoren, "
              "ordnet bekannte Personen zu und ermöglicht das Benennen neuer Personen.\n\n"
              "Personen-, Bilddatenbank, Warteschlange, Backups und Vorschaubilder werden "
              "im ausgewählten Datenordner gespeichert. Allgemeine Programmeinstellungen "
              "liegen weiterhin im Benutzerprofil."),
        justify="center", wraplength=390,
    ).pack()
    tk.Button(rahmen, text="Schließen", command=dialog.destroy).pack(pady=(16, 0))


def programmdateien_ablageort_waehlen():
    alter_ordner = ordner_programmdateien()
    auswahl = filedialog.askdirectory(
        parent=fenster,
        title="Ablageort für Programmdateien wählen",
        initialdir=str(alter_ordner),
        mustexist=True,
    )
    if not auswahl:
        return

    neuer_ordner = Path(auswahl).expanduser().resolve()
    neuer_ordner.mkdir(parents=True, exist_ok=True)
    if neuer_ordner == alter_ordner.resolve():
        return

    # Datenbankdateien und zugehörige Nutzerdaten in den neuen Ordner übernehmen.
    for dateiname in ("personen.pkl", "bilder.pkl", "warteschlange.pkl", "einstellungen.pkl"):
        quelle, ziel = alter_ordner / dateiname, neuer_ordner / dateiname
        if quelle.exists() and not ziel.exists():
            shutil.copy2(quelle, ziel)

    for ordnername in ("backups", ".thumbnails"):
        quelle, ziel = alter_ordner / ordnername, neuer_ordner / ordnername
        if quelle.is_dir() and not ziel.exists():
            shutil.copytree(quelle, ziel, dirs_exist_ok=True)

    EINSTELLUNGEN["DATEN_ORDNER"] = str(neuer_ordner)
    speichere_einstellungen(EINSTELLUNGEN)
    messagebox.showinfo(
        "Ablageort gespeichert",
        f"Programmdateien werden ab jetzt hier gespeichert:\n{neuer_ordner}",
        parent=fenster,
    )


fenster = tk.Tk()
_modernisiere_ttk(fenster)
fenster.title("NeuraPix")

# Kleiner, zentrierter Startbildschirm; die Arbeitsoberfläche wird erst
# nach Auswahl eines Bildordners eingeblendet.
fenster.update_idletasks()
fenster.minsize(220, 180)
zentriere_fenster(0.25)
fenster.grid_columnconfigure(0, weight=1)
fenster.grid_rowconfigure(1, weight=1)

menueleiste = tk.Menu(fenster, tearoff=0, background="#FFFFFF", foreground="#17233F", activebackground="#3157C8", activeforeground="#FFFFFF", borderwidth=0)
datei_menu = tk.Menu(menueleiste, tearoff=0, background="#FFFFFF", foreground="#17233F", activebackground="#3157C8", activeforeground="#FFFFFF", borderwidth=0)
datei_menu.add_command(label="Analyseordner verwalten...", command=analyseordner_verwalten)
datei_menu.add_command(label="Bilder ansehen", command=bilder_ansehen)
datei_menu.add_command(label="Einstellungen...", command=einstellungen_oeffnen)
datei_menu.add_separator()
datei_menu.add_command(label="Beenden", command=beenden)
menueleiste.add_cascade(label="Datei", menu=datei_menu)

datenbank_menu = tk.Menu(menueleiste, tearoff=0, background="#FFFFFF", foreground="#17233F", activebackground="#3157C8", activeforeground="#FFFFFF", borderwidth=0)
datenbank_menu.add_command(label="Backup jetzt erstellen...", command=datenbank_backup)
datenbank_menu.add_command(label="Datenbank prüfen...", command=datenbank_pruefen)
datenbank_menu.add_command(label="Bildduplikate suchen...", command=datenbank_duplikate_suchen)
datenbank_menu.add_separator()
datenbank_menu.add_command(label="Datenbank exportieren...", command=datenbank_exportieren)
datenbank_menu.add_command(label="Datenbank wiederherstellen...", command=datenbank_wiederherstellen)
menueleiste.add_cascade(label="Datenbank", menu=datenbank_menu)

hilfe_menu = tk.Menu(menueleiste, tearoff=0, background="#FFFFFF", foreground="#17233F", activebackground="#3157C8", activeforeground="#FFFFFF", borderwidth=0)
hilfe_menu.add_command(label="Hilfe", command=hilfe_oeffnen)
hilfe_menu.add_command(label="Info", command=info_oeffnen)
menueleiste.add_cascade(label="Hilfe", menu=hilfe_menu)
fenster.config(menu=menueleiste)
fenster.protocol("WM_DELETE_WINDOW", fenster_schliessen)
fenster.bind("<Deactivate>", _kontextmenue_fokusverlust, add="+")
try:
    erstelle_backup("automatisch", erzwingen=False)
except Exception as exc:
    print(f"Automatisches Datenbank-Backup fehlgeschlagen: {exc}")

ordner_info = tk.Label(fenster, text="Bitte Analyseordner hinzufügen", anchor="w", wraplength=1050, cursor="hand2", fg="#2457a7")
ordner_info.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
ordner_info.bind("<Button-1>", lambda _event: analyseordner_verwalten())

karussell_frame = tk.Frame(fenster, bg="#EAF0FC")
karussell_frame.grid(row=1, column=0, sticky="nsew")
karussell_frame.grid_columnconfigure(0, weight=1)
karussell_frame.grid_rowconfigure(0, weight=1)
karussell = BilderKarussell(karussell_frame)
karussell.set_aktiv(EINSTELLUNGEN["KARUSSELL_AKTIV"])

thumbnail_canvas = tk.Canvas(karussell_frame, highlightthickness=0, bg="#EAF0FC", bd=0)
thumbnail_scrollbar = ttk.Scrollbar(karussell_frame, orient="vertical", command=thumbnail_canvas.yview)
thumbnail_canvas.configure(yscrollcommand=thumbnail_scrollbar.set)
thumbnail_inhalt = tk.Frame(thumbnail_canvas, bg="#EAF0FC")
thumbnail_window = thumbnail_canvas.create_window((0, 0), window=thumbnail_inhalt, anchor="nw")
thumbnail_scrollbar.grid(row=0, column=1, sticky="ns")
thumbnail_canvas.grid(row=0, column=0, sticky="nsew")
thumbnail_canvas.grid_remove()
thumbnail_scrollbar.grid_remove()

def _thumbnail_inhalt_groesse(_event=None):
    thumbnail_canvas.configure(scrollregion=thumbnail_canvas.bbox("all"))

def _thumbnail_canvas_groesse(event):
    thumbnail_canvas.itemconfigure(thumbnail_window, width=event.width)

thumbnail_inhalt.bind("<Configure>", _thumbnail_inhalt_groesse)
thumbnail_canvas.bind("<Configure>", _thumbnail_canvas_groesse)

fortschritt_frame = tk.Frame(fenster, bg="#EAF0FC")
fortschritt_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
fortschritt_frame.grid_columnconfigure(1, weight=1)
status_bild = tk.Label(fortschritt_frame, text="Bereit", anchor="w")
status_bild.grid(row=0, column=0, sticky="w", padx=(0, 12))
fortschritt = ttk.Progressbar(fortschritt_frame, mode="determinate")
fortschritt.grid(row=0, column=1, sticky="ew")
restzeit_label = tk.Label(fortschritt_frame, text="", anchor="e", font=("Arial", 9))
restzeit_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))

namens_frame = tk.Frame(fenster, bg="#FFFFFF", relief="flat", borderwidth=0, highlightthickness=1, highlightbackground="#D8E2F4")
namens_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=4)
namens_frame.grid_remove()

ergebnis_label = tk.Label(fenster, text="Bereit", font=("Arial", 11))
ergebnis_label.grid(row=4, column=0, sticky="ew", padx=10, pady=3)
if not EINSTELLUNGEN["STATUSLEISTE_AKTIV"]:
    ergebnis_label.grid_remove()

button_frame = tk.Frame(fenster, bg="#EAF0FC")
button_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=(4, 10))
analyse_button = tk.Button(
    button_frame, text="Bilder analysieren", command=analyse_starten, state="disabled",
    bg="#3157C8", fg="#FFFFFF", activebackground="#2446AA", activeforeground="#FFFFFF",
    relief="flat", bd=0, highlightthickness=0, padx=18, pady=9,
    font=("DejaVu Sans", 10, "bold"), cursor="hand2"
)
analyse_button.grid(row=0, column=0, padx=5)
stop_button = tk.Button(button_frame, text="Stop", command=analyse_stoppen)
stop_button.grid(row=0, column=1, padx=5)
stop_button.grid_remove()
status_label = tk.Label(button_frame, text="Bereit", anchor="e")
status_label.grid(row=0, column=2, sticky="e", padx=5)
warteschlange_button = tk.Button(
    button_frame,
    text="Unbekannte Gesichter zur Zuordnung: 0",
    command=warteschlange_bearbeiten_gui,
    state="disabled",
)
warteschlange_button.grid(row=1, column=0, columnspan=3, sticky="ew", padx=5, pady=(6, 0))
button_frame.grid_columnconfigure(2, weight=1)

# Startansicht: nur Ordnersymbol und Auswahltext anzeigen.
fenster.config(menu=menueleiste)
ordner_info.grid_remove()
karussell_frame.grid_remove()
fortschritt_frame.grid_remove()
button_frame.grid_remove()
ergebnis_label.grid_remove()
start_frame = tk.Frame(fenster)
start_frame.place(relx=0.5, rely=0.5, anchor="center")
ordner_symbol = tk.Label(start_frame, text="📁", font=("DejaVu Sans", 52), cursor="hand2")
ordner_symbol.pack(pady=(0, 8))
ordner_symbol.bind("<Button-1>", lambda _event: ordner_auswaehlen())
ordner_text = tk.Label(start_frame, text="Bitte Analyseordner wählen", font=("Arial", 15), cursor="hand2")
ordner_text.pack()
ordner_text.bind("<Button-1>", lambda _event: ordner_auswaehlen())
start_frame.bind("<Button-1>", lambda _event: ordner_auswaehlen())

if analyse_ordner:
    hauptoberflaeche_anzeigen()
    analyseordner_info_aktualisieren()
    zeige_thumbnails(alle_analysebilder())

warteschlange_poll()

# Dem NeuraPix-Starter melden, dass die GUI vollständig aufgebaut ist.
# Der Splashscreen wartet zusätzlich seine Mindestanzeigezeit von drei Sekunden ab.
_bereit_datei = os.environ.get("NEURAPIX_READY_FILE")
if _bereit_datei:
    try:
        Path(_bereit_datei).write_text("ready", encoding="utf-8")
    except OSError as exc:
        print(f"Bereitschaftsmeldung an Starter fehlgeschlagen: {exc}")

fenster.mainloop()

# Nach Ende der Tk-Hauptschleife alle Hintergrundkomponenten schließen.
# Einige native Bibliotheken (GTK/ONNX/OpenCV) können eigene Threads halten.
# Nach dem geordneten Tk-/Tray-Shutdown darf der Prozess deshalb nicht hängen bleiben.
try:
    tray_beenden()
except Exception:
    pass

try:
    sys.stdout.flush()
    sys.stderr.flush()
except Exception:
    pass

os._exit(0)
