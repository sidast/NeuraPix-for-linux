from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk
import cv2


class BilderKarussell:
    """Animierte Drei-Bilder-Ansicht; leere Randpositionen bleiben leer."""

    def __init__(self, parent):
        self.canvas = tk.Canvas(parent, highlightthickness=0, background=parent.cget("background"))
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=8, pady=6)
        self.dateien = []
        self.index = None
        self.center_override = None
        self._pil_cache = {}
        self._tk_refs = []
        self._letzter_aufbau = None
        self.aktiv = True
        self.canvas.bind("<Configure>", self._bei_groesse)


    def set_aktiv(self, aktiv):
        self.aktiv = bool(aktiv)
        if self.index is not None:
            self._zeichnen(self.index)

    def rahmen_entfernen(self):
        """Entfernt die markierte Bildkopie und zeigt das Originalbild."""
        self.center_override = None
        if self.index is not None:
            self._zeichnen(self.index)

    def leere_anzeige(self):
        self.index = None
        self.center_override = None
        self.canvas.delete("all")
        self._tk_refs = []

    def _lade_bild(self, index):
        if index < 0 or index >= len(self.dateien):
            return None
        pfad = str(self.dateien[index])
        if index == self.index and self.center_override is not None:
            return self.center_override.copy()
        if pfad not in self._pil_cache:
            try:
                with Image.open(pfad) as bild:
                    self._pil_cache[pfad] = bild.convert("RGB")
            except (OSError, ValueError):
                return None
        return self._pil_cache[pfad].copy()

    @staticmethod
    def _cv_to_pil(bild_cv):
        if bild_cv is None:
            return None
        return Image.fromarray(cv2.cvtColor(bild_cv, cv2.COLOR_BGR2RGB))

    def zeige(self, dateien, index, bild_cv=None, animieren=False):
        self.dateien = list(dateien)
        vorheriger_index = self.index
        vorheriges_override = self.center_override
        neuer_override = self._cv_to_pil(bild_cv) if bild_cv is not None else None

        if (self.aktiv and animieren and vorheriger_index is not None and index == vorheriger_index + 1
                and self.canvas.winfo_width() > 10 and self.canvas.winfo_height() > 10):
            self._animieren(vorheriger_index, index, vorheriges_override, neuer_override)

        self.index = index
        self.center_override = neuer_override
        self._zeichnen(index)

    def _bei_groesse(self, _event=None):
        if self.index is not None:
            self._zeichnen(self.index)

    def _zeichnen(self, index):
        self.canvas.delete("all")
        self._tk_refs = []
        breite = max(self.canvas.winfo_width(), 1)
        hoehe = max(self.canvas.winfo_height(), 1)
        if self.aktiv:
            slots = [
                (index - 1, 0.17 * breite, 0.52, 0.56 * breite, 0.94 * hoehe),
                (index,     0.50 * breite, 1.00, 0.56 * breite, 0.94 * hoehe),
                (index + 1, 0.83 * breite, 0.52, 0.56 * breite, 0.94 * hoehe),
            ]
        else:
            slots = [(index, 0.50 * breite, 1.00, 0.92 * breite, 0.94 * hoehe)]
        for bild_index, x, skalierung, max_w, max_h in slots:
            bild = self._lade_bild(bild_index)
            if bild is None:
                continue
            max_w = max(int(max_w * skalierung), 1)
            max_h = max(int(max_h * skalierung), 1)
            bild.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            tk_bild = ImageTk.PhotoImage(bild)
            self._tk_refs.append(tk_bild)
            self.canvas.create_image(x, hoehe / 2, image=tk_bild, anchor="center")

    def _animieren(self, alter_index, neuer_index, alter_override, neuer_override):
        breite = max(self.canvas.winfo_width(), 1)
        hoehe = max(self.canvas.winfo_height(), 1)
        eintraege = [
            (alter_index - 1, 0.17, 0.52, -0.16, 0.52, None),
            (alter_index,     0.50, 1.00, 0.17, 0.52, alter_override),
            (alter_index + 1, 0.83, 0.52, 0.50, 1.00, None),
            (alter_index + 2, 1.16, 0.52, 0.83, 0.52, None),
        ]
        for schritt in range(1, 9):
            t = schritt / 8
            self.canvas.delete("all")
            self._tk_refs = []
            for bild_index, x_start, s_start, x_ende, s_ende, override in eintraege:
                bild = None
                if bild_index == alter_index and override is not None:
                    bild = override.copy()
                elif bild_index == neuer_index and neuer_override is not None:
                    bild = neuer_override.copy()
                else:
                    bild = self._lade_bild(bild_index)
                if bild is None:
                    continue
                x = (x_start + (x_ende - x_start) * t) * breite
                skalierung = s_start + (s_ende - s_start) * t
                max_w = max(int(0.56 * breite * skalierung), 1)
                max_h = max(int(0.94 * hoehe * skalierung), 1)
                bild.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                tk_bild = ImageTk.PhotoImage(bild)
                self._tk_refs.append(tk_bild)
                self.canvas.create_image(x, hoehe / 2, image=tk_bild, anchor="center")
            self.canvas.update_idletasks()
            self.canvas.update()
            self.canvas.after(18)
