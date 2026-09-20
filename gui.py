"""customtkinter інтерфейс завантажувача відео."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter
from pathlib import Path
from tkinter import Menu, filedialog, messagebox

import customtkinter as ctk

import downloader

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Smart Attic")
        self.geometry("600x470")
        self.minsize(540, 440)

        self.output_dir = Path.home() / "Downloads"
        self.formats: list[dict] = []
        self.last_file: Path | None = None

        self._build_widgets()
        self.after(400, self._show_disclaimer_once)
        self.after(600, self._report_ytdlp_version)

    # ---------- інтерфейс ----------

    def _build_widgets(self):
        ctk.CTkLabel(self, text="Smart Attic", font=("", 20, "bold")).pack(padx=16, pady=(16, 4))

        row_url = ctk.CTkFrame(self, fg_color="transparent")
        row_url.pack(fill="x", padx=16, pady=6)
        self.entry_url = ctk.CTkEntry(
            row_url, placeholder_text="Встав посилання на YouTube або Facebook"
        )
        self.entry_url.pack(side="left", fill="x", expand=True)
        self._enable_paste(self.entry_url)
        self.btn_analyze = ctk.CTkButton(
            row_url, text="Аналізувати", width=120, command=self.on_analyze
        )
        self.btn_analyze.pack(side="left", padx=(8, 0))

        row_quality = ctk.CTkFrame(self, fg_color="transparent")
        row_quality.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row_quality, text="Якість:").pack(side="left")
        self.combo_quality = ctk.CTkComboBox(row_quality, values=[""], state="disabled")
        self.combo_quality.pack(side="left", fill="x", expand=True, padx=(8, 0))

        row_folder = ctk.CTkFrame(self, fg_color="transparent")
        row_folder.pack(fill="x", padx=16, pady=6)
        self.label_folder = ctk.CTkLabel(
            row_folder, text=f"Папка: {self.output_dir}", anchor="w"
        )
        self.label_folder.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            row_folder, text="Обрати...", width=100, command=self.on_choose_folder
        ).pack(side="left", padx=(8, 0))

        self.btn_download = ctk.CTkButton(self, text="Download", command=self.on_download)
        self.btn_download.pack(padx=16, pady=(10, 6), fill="x")

        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.pack(padx=16, pady=6, fill="x")

        self.btn_play = ctk.CTkButton(
            self,
            text="▶ Відтворити останній файл",
            fg_color="gray50",
            hover_color="gray40",
            command=self.on_play_last,
        )
        self.btn_play.pack(padx=16, pady=6, fill="x")

        self.label_status = ctk.CTkLabel(self, text="Готово до роботи", anchor="w")
        self.label_status.pack(padx=16, pady=(6, 2), fill="x")

        row_tools = ctk.CTkFrame(self, fg_color="transparent")
        row_tools.pack(fill="x", padx=16, pady=(0, 12))
        self.label_engine = ctk.CTkLabel(
            row_tools, text="yt-dlp: перевіряю...", anchor="w", text_color="gray50"
        )
        self.label_engine.pack(side="left", fill="x", expand=True)
        self.btn_update = ctk.CTkButton(
            row_tools, text="Оновити yt-dlp", width=140, command=self.on_update_engine
        )
        self.btn_update.pack(side="left", padx=(8, 0))

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
        self.label_status.configure(text="Обери якість і натисни Download")

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
        self.btn_download.configure(state="normal", text="Download")
        messagebox.showinfo("Успіх", "Відео завантажено:\n" + str(result_path))

    def _download_failed(self, error: str):
        self.btn_download.configure(state="normal", text="Download")
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
