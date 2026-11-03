#!/usr/bin/env python3
"""NeuraPix-Starter mit Splashscreen; startet die eigentliche GUI separat."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parent
ICON = ROOT / "branding" / "hicolor" / "512x512" / "apps" / "neurapix.png"
LOGO = ROOT / "branding" / "neurapix-logo-master.png"

def main():
    ready = Path(tempfile.gettempdir()) / f"neurapix-ready-{os.getpid()}"
    ready.unlink(missing_ok=True)
    env = os.environ.copy()
    env["NEURAPIX_READY_FILE"] = str(ready)

    splash = tk.Tk()
    splash.overrideredirect(True)
    splash.configure(bg="#111528")
    splash.attributes("-topmost", True)
    width, height = 440, 390
    x = (splash.winfo_screenwidth() - width) // 2
    y = (splash.winfo_screenheight() - height) // 2
    splash.geometry(f"{width}x{height}+{x}+{y}")
    try:
        source = LOGO if LOGO.exists() else ICON
        image = Image.open(source).convert("RGBA")
        image.thumbnail((230, 230), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        label = tk.Label(splash, image=photo, bg="#111528", borderwidth=0)
        label.image = photo
        label.pack(pady=(26, 12))
    except Exception:
        tk.Label(splash, text="NeuraPix", fg="white", bg="#111528",
                 font=("DejaVu Sans", 30, "bold")).pack(pady=70)
    tk.Label(splash, text="NeuraPix", fg="#FFFFFF", bg="#111528",
             font=("DejaVu Sans", 25, "bold")).pack()
    tk.Label(splash, text="Gar nicht mal so unintelligente Bildverwaltung",
             fg="#B8C5F5", bg="#111528",
             font=("DejaVu Sans", 10)).pack(pady=(5, 18))
    status = tk.Label(splash, text="Programm wird geladen …", fg="#D8DDF2",
                      bg="#111528", font=("DejaVu Sans", 9))
    status.pack()
    bar = tk.Canvas(splash, width=330, height=7, bg="#303750",
                    highlightthickness=0)
    bar.pack(pady=16)
    bar.create_rectangle(0, 0, 330, 7, fill="#7188FF", outline="")
    splash.update()

    started = time.monotonic()
    process = subprocess.Popen([sys.executable, str(ROOT / "gui.py")], cwd=ROOT, env=env)
    def check():
        elapsed = time.monotonic() - started
        if process.poll() is not None:
            splash.destroy()
            return
        if ready.exists() and elapsed >= 3:
            ready.unlink(missing_ok=True)
            splash.destroy()
            return
        splash.after(100, check)
    splash.after(100, check)
    splash.mainloop()

if __name__ == "__main__":
    main()
