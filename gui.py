"""customtkinter інтерфейс завантажувача відео."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter
import webbrowser
from pathlib import Path
from tkinter import Menu, filedialog, messagebox

import customtkinter as ctk

import downloader

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Підвал: автор і посилання на сайт автора.
AUTHOR_NAME = "Григорій Йовдій"
AUTHOR_URL = "https://gregory-ivd.github.io/smart-attic/"

BG = "#0F172A"
CARD = "#1E293B"
FIELD = "#0F172A"
ACCENT = "#6366F1"
ACCENT_HOVER = "#4F46E5"
MUTED = "#94A3B8"
TEXT = "#F1F5F9"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Smart Attic")
        self.geometry("640x640")
        self.minsize(580, 600)
        self.configure(fg_color=BG)

        self.output_dir = Path.home() / "Downloads"
        self.formats: list[dict] = []
        self.last_file: Path | None = None

        self._build_widgets()
        self.after(400, self._show_disclaimer_once)
        self.after(600, self._report_ytdlp_version)

    # ---------- інтерфейс ----------

    def _build_widgets(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(22, 10))
        ctk.CTkLabel(
            header, text="Smart Attic", font=("Segoe UI", 26, "bold"), text_color=TEXT
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Завантажувач відео · без реклами · рушій оновлюється одним кліком",
            font=("Segoe UI", 12),
            text_color=MUTED,
        ).pack(anchor="w")

        # Картка: посилання і якість
        card_src = self._card()
        row_url = ctk.CTkFrame(card_src, fg_color="transparent")
        row_url.pack(fill="x", padx=16, pady=(16, 8))
        self.entry_url = ctk.CTkEntry(
            row_url,
            height=40,
            corner_radius=10,
            fg_color=FIELD,
            border_color="#334155",
            placeholder_text="Встав посилання на YouTube або Facebook",
        )
        self.entry_url.pack(side="left", fill="x", expand=True)
        self._enable_paste(self.entry_url)
        self.btn_analyze = ctk.CTkButton(
            row_url,
            text="Аналізувати",
            width=120,
            height=40,
            corner_radius=10,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self.on_analyze,
        )
        self.btn_analyze.pack(side="left", padx=(8, 0))

        row_quality = ctk.CTkFrame(card_src, fg_color="transparent")
        row_quality.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkLabel(row_quality, text="Якість", text_color=MUTED).pack(side="left")
        self.combo_quality = ctk.CTkComboBox(
            row_quality,
            values=[""],
            state="disabled",
            height=36,
            corner_radius=10,
            fg_color=FIELD,
            border_color="#334155",
            button_color="#334155",
        )
        self.combo_quality.pack(side="left", fill="x", expand=True, padx=(12, 0))

        # Картка: папка
        card_dst = self._card()
        row_folder = ctk.CTkFrame(card_dst, fg_color="transparent")
        row_folder.pack(fill="x", padx=16, pady=14)
        self.label_folder = ctk.CTkLabel(
            row_folder, text=f"Папка: {self.output_dir}", anchor="w", text_color=TEXT
        )
        self.label_folder.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            row_folder,
            text="Обрати…",
            width=100,
            height=34,
            corner_radius=10,
            fg_color="#334155",
            hover_color="#475569",
            command=self.on_choose_folder,
        ).pack(side="left", padx=(8, 0))

        self.btn_download = ctk.CTkButton(
            self,
            text="Завантажити",
            height=48,
            corner_radius=12,
            font=("Segoe UI", 16, "bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self.on_download,
        )
        self.btn_download.pack(padx=24, pady=(6, 10), fill="x")

        self.progress = ctk.CTkProgressBar(
            self, height=10, corner_radius=5, progress_color=ACCENT, fg_color=CARD
        )
        self.progress.set(0)
        self.progress.pack(padx=24, pady=(0, 6), fill="x")

        self.label_status = ctk.CTkLabel(
            self, text="Готово до роботи", anchor="w", text_color=MUTED
        )
        self.label_status.pack(padx=24, pady=(0, 8), fill="x")

        self.btn_play = ctk.CTkButton(
            self,
            text="▶  Відтворити останній файл",
            height=38,
            corner_radius=10,
            fg_color=CARD,
            hover_color="#334155",
            command=self.on_play_last,
        )
        self.btn_play.pack(padx=24, pady=(0, 12), fill="x")

        # Рушій
        row_tools = ctk.CTkFrame(self, fg_color="transparent")
        row_tools.pack(fill="x", padx=24, pady=(0, 8))
        self.label_engine = ctk.CTkLabel(
            row_tools, text="yt-dlp: перевіряю...", anchor="w", text_color=MUTED
        )
        self.label_engine.pack(side="left", fill="x", expand=True)
        self.btn_update = ctk.CTkButton(
            row_tools,
            text="Оновити yt-dlp",
            width=140,
            height=30,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
            border_color=ACCENT,
            text_color=TEXT,
            hover_color=CARD,
            command=self.on_update_engine,
        )
        self.btn_update.pack(side="left", padx=(8, 0))

        # Підвал
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=24, pady=(0, 14))
        ctk.CTkFrame(footer, height=1, fg_color="#334155").pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            footer, text="Розробник:", text_color=MUTED, font=("Segoe UI", 12)
        ).pack(side="left")
        link = ctk.CTkLabel(
            footer,
            text=AUTHOR_NAME,
            text_color="#818CF8",
            cursor="hand2",
            font=("Segoe UI", 12, "underline"),
        )
        link.pack(side="left", padx=(6, 0))
        link.bind("<Button-1>", lambda _e: webbrowser.open(AUTHOR_URL))

    def _card(self):
        card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14)
        card.pack(fill="x", padx=24, pady=6)
        return card

    def _enable_paste(self, entry):
        """Ctrl+V прив'язаний Tkinter до символу 'v' — на нелатинських розкладках
        клавіатури (укр./рос.) фізична клавіша V видає інший символ, і стандартна
        комбінація просто не спрацьовує. Прив'язуємось до keycode (фізичної
        клавіші), а не до символу, і додаємо запасний варіант — вставку через
        контекстне меню правою кнопкою миші."""

        def paste_from_clipboard(_event=None):
            try:
                entry.insert("end", self.clipboard_get())
            except tkinter.TclError:
                pass
            return "break"

        def on_control_key(event):
            if event.keycode == 86:  # фізична клавіша V
                return paste_from_clipboard()
            return None

        entry.bind("<Control-KeyPress>", on_control_key)

        menu = Menu(entry, tearoff=0)
        menu.add_command(label="Вставити", command=paste_from_clipboard)

        def show_menu(event):
            menu.tk_popup(event.x_root, event.y_root)

        entry.bind("<Button-3>", show_menu)

    def _show_disclaimer_once(self):
        messagebox.showinfo(
            "Нагадування",
            "Завантажуйте лише те відео, на яке ви маєте право "
            "(власний контент, публічно дозволене використання тощо).",
        )

    # ---------- рушій ----------

    def _report_ytdlp_version(self):
        def worker():
            exe = downloader.find_ytdlp()
            if exe is None:
                text = "yt-dlp: не знайдено — натисни «Оновити yt-dlp»"
            else:
                text = f"yt-dlp: {downloader.ytdlp_version(exe)}"
            self.after(0, lambda: self.label_engine.configure(text=text))

        threading.Thread(target=worker, daemon=True).start()

    def on_update_engine(self):
        self.btn_update.configure(state="disabled", text="Оновлюю...")

        def worker():
            try:
                version = downloader.update_ytdlp()
                self.after(0, lambda: self._update_engine_done(version))
            except Exception as exc:
                self.after(0, lambda: self._update_engine_failed(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _update_engine_done(self, version: str):
        self.btn_update.configure(state="normal", text="Оновити yt-dlp")
        self.label_engine.configure(text=f"yt-dlp: {version}")
        self.label_status.configure(text="Рушій оновлено")

    def _update_engine_failed(self, error: str):
        self.btn_update.configure(state="normal", text="Оновити yt-dlp")
        messagebox.showerror("Помилка", error)

    # ---------- аналіз ----------

    def on_analyze(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("Увага", "Спочатку встав посилання на відео.")
            return
        self.btn_analyze.configure(state="disabled", text="Аналіз...")
        self.label_status.configure(text="Отримую список доступних якостей...")
        threading.Thread(target=self._analyze_worker, args=(url,), daemon=True).start()

    def _analyze_worker(self, url: str):
        try:
            formats = downloader.get_formats(url)
            self.after(0, lambda: self._analyze_done(formats))
        except downloader.DownloaderError as exc:
            self.after(0, lambda: self._analyze_failed(str(exc)))
        except Exception as exc:
            self.after(0, lambda: self._analyze_failed("Неочікувана помилка: " + str(exc)))

    def _analyze_done(self, formats: list[dict]):
        self.formats = formats
        labels = [f["label"] for f in formats]
        self.combo_quality.configure(values=labels, state="readonly")
        if labels:
            self.combo_quality.set(labels[0])
        self.btn_analyze.configure(state="normal", text="Аналізувати")
        self.label_status.configure(text="Обери якість і натисни «Завантажити»")

    def _analyze_failed(self, error: str):
        self.btn_analyze.configure(state="normal", text="Аналізувати")
        self.label_status.configure(text="Помилка аналізу")
        messagebox.showerror("Помилка", error)

    # ---------- завантаження ----------

    def on_choose_folder(self):
        chosen = filedialog.askdirectory(initialdir=str(self.output_dir))
        if chosen:
            self.output_dir = Path(chosen)
            self.label_folder.configure(text=f"Папка: {self.output_dir}")

    def on_download(self):
        url = self.entry_url.get().strip()
        selected = self.combo_quality.get()
        match = next((f for f in self.formats if f["label"] == selected), None)
        if not url or match is None:
            messagebox.showwarning("Увага", "Спочатку проаналізуй посилання і обери якість.")
            return
        self.btn_download.configure(state="disabled", text="Завантаження...")
        self.progress.set(0)
        self.label_status.configure(text="Починаю завантаження...")
        threading.Thread(
            target=self._download_worker, args=(url, match["format_id"]), daemon=True
        ).start()

    def _download_worker(self, url: str, format_id: str):
        def progress_callback(percent, text):
            self.after(0, lambda: self._update_progress(percent, text))

        try:
            result_path = downloader.download(
                url, format_id, self.output_dir, progress_callback
            )
            self.after(0, lambda: self._download_done(result_path))
        except downloader.DownloaderError as exc:
            self.after(0, lambda: self._download_failed(str(exc)))
        except Exception as exc:
            self.after(0, lambda: self._download_failed("Неочікувана помилка: " + str(exc)))

    def _update_progress(self, percent: float, text: str):
        self.progress.set(max(0.0, min(percent / 100, 1.0)))
        self.label_status.configure(text=text)

    def _download_done(self, result_path: Path):
        self.last_file = result_path
        self.progress.set(1)
        self.label_status.configure(text="Готово!")
        self.btn_download.configure(state="normal", text="Завантажити")
        messagebox.showinfo("Успіх", "Відео завантажено:\n" + str(result_path))

    def _download_failed(self, error: str):
        self.btn_download.configure(state="normal", text="Завантажити")
        self.label_status.configure(text="Помилка завантаження")
        messagebox.showerror("Помилка", error)

    def on_play_last(self):
        if not self.last_file or not Path(self.last_file).exists():
            messagebox.showwarning(
                "Увага", "Файл не знайдено — можливо, його перемістили або видалили."
            )
            return
        if os.name == "nt":
            os.startfile(str(self.last_file))
        else:
            subprocess.Popen(["xdg-open", str(self.last_file)])
