"""Обгортка над зовнішнім yt-dlp.exe: аналіз доступних форматів і завантаження з прогресом.

Чому саме зовнішній yt-dlp, а не вбудована бібліотека yt_dlp.
YouTube ламає видобувач приблизно раз на кілька тижнів. Якщо yt_dlp вшитий
усередину .exe, єдиний спосіб полагодити застосунок — перезібрати і роздати
його заново. Зовнішній бінарник оновлюється однією кнопкою і живе окремо
від застосунку.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

# Nightly, а не stable. Перевірено 20.09.2026: stable 2026.08.19 віддає
# HTTP 403 на медіа-URL YouTube, nightly 2026.09.16 качає нормально.
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.exe"

# Щоб у GUI-застосунку не блимало чорне вікно консолі на кожен виклик.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class DownloaderError(Exception):
    pass


def app_dir() -> Path:
    """Папка поруч із .exe — і в dev-режимі, і в зібраному вигляді."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def tools_dir() -> Path:
    """Приватна папка застосунку для yt-dlp.exe."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base) / "SmartAtticDownloader"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_ytdlp() -> Path | None:
    """Портативна копія поруч із .exe → приватна копія → системна з PATH."""
    for candidate in (app_dir() / "yt-dlp.exe", tools_dir() / "yt-dlp.exe"):
        if candidate.is_file():
            return candidate
    found = shutil.which("yt-dlp")
    return Path(found) if found else None


def find_ffmpeg() -> Path | None:
    """Бандлений ffmpeg → поруч із .exe → системний з PATH."""
    bundled = Path(getattr(sys, "_MEIPASS", app_dir())) / "ffmpeg" / "ffmpeg.exe"
    if bundled.is_file():
        return bundled
    local = app_dir() / "ffmpeg.exe"
    if local.is_file():
        return local
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def _run(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )


def ytdlp_version(exe: Path) -> str:
    try:
        return _run([str(exe), "--version"], timeout=30).stdout.strip()
    except Exception:
        return "невідомо"


def ensure_ytdlp(progress_callback=None) -> Path:
    """Повертає шлях до yt-dlp.exe, за потреби завантаживши свіжий білд."""
    exe = find_ytdlp()
    if exe:
        return exe
    return install_ytdlp(progress_callback)


def install_ytdlp(progress_callback=None) -> Path:
    """Тягне свіжий yt-dlp.exe у приватну папку застосунку."""
    target = tools_dir() / "yt-dlp.exe"
    tmp = target.with_suffix(".part")
    try:
        with urllib.request.urlopen(YTDLP_URL, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp, "wb") as fh:
                while True:
                    chunk = response.read(262144)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if progress_callback and total:
                        progress_callback(done / total, "Завантажую yt-dlp...")
        tmp.replace(target)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise DownloaderError(f"Не вдалося завантажити yt-dlp: {exc}") from exc

    if not ytdlp_version(target):
        raise DownloaderError("Завантажений yt-dlp.exe не запускається.")
    return target


def update_ytdlp() -> str:
    """Оновлює наявний yt-dlp до свіжого nightly. Повертає версію після оновлення."""
    exe = find_ytdlp()
    if exe is None:
        exe = install_ytdlp()
        return ytdlp_version(exe)

    result = _run([str(exe), "--update-to", "nightly"], timeout=300)
    if result.returncode != 0:
        # Системну копію могло бути встановлено пакетним менеджером — тоді
        # самооновлення заборонене. Ставимо власну копію поруч із застосунком.
        exe = install_ytdlp()
    return ytdlp_version(exe)


def _format_size(size_bytes) -> str:
    if not size_bytes:
        return "розмір невідомий"
    mb = size_bytes / 1024 / 1024
    if mb < 1:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{mb:.0f} MB"


def get_formats(url: str) -> list[dict]:
    """Список форматів для вибору, від найкращого до найгіршого + audio-only."""
    exe = ensure_ytdlp()
    args = [str(exe), "--no-warnings", "--no-playlist", "-J", url]
    try:
        result = _run(args, timeout=180)
    except subprocess.TimeoutExpired as exc:
        raise DownloaderError("Сайт не відповів за три хвилини.") from exc

    if result.returncode != 0:
        raise DownloaderError(
            "Не вдалося отримати інформацію про відео: " + _last_error(result.stderr)
        )
    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise DownloaderError("yt-dlp повернув невідому відповідь.") from exc

    formats = info.get("formats") or []
    by_height: dict[int, dict] = {}
    for fmt in formats:
        height = fmt.get("height")
        if not height or fmt.get("vcodec") in (None, "none"):
            continue
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        previous = by_height.get(height)
        if previous is None or (size or 0) > (previous.get("_size") or 0):
            by_height[height] = {"_size": size, "ext": fmt.get("ext") or "mp4"}

    items: list[dict] = []
    for height in sorted(by_height, reverse=True):
        entry = by_height[height]
        items.append(
            {
                "label": f"{height}p ({entry['ext']}, {_format_size(entry['_size'])})",
                "format_id": (
                    f"bestvideo[ext=mp4][height<={height}]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={height}]+bestaudio/"
                    f"best[height<={height}]"
                ),
            }
        )

    audio = [f for f in formats if f.get("acodec") not in (None, "none")
             and f.get("vcodec") in (None, "none")]
    if audio:
        best_audio = max(audio, key=lambda f: f.get("abr") or 0)
        size = best_audio.get("filesize") or best_audio.get("filesize_approx")
        items.append(
            {
                "label": f"Тільки аудіо ({best_audio.get('ext') or 'm4a'}, {_format_size(size)})",
                "format_id": "bestaudio/best",
            }
        )

    items.insert(0, {
        "label": "Найкраща доступна якість",
        "format_id": "bestvideo*+bestaudio/best",
    })
    return items


def _last_error(stderr: str) -> str:
    lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    errors = [ln for ln in lines if ln.upper().startswith("ERROR")]
    tail = errors[-1] if errors else (lines[-1] if lines else "причина невідома")
    return tail.removeprefix("ERROR:").strip()


_PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")


def download(url: str, format_id: str, output_dir, progress_callback=None) -> Path:
    """Завантажує відео у форматі format_id. progress_callback(percent, status_text)."""
    exe = ensure_ytdlp()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Ім'я готового файлу забираємо не з логів, а окремим каналом —
    # так воно не змішується з рядками прогресу.
    fd, result_file = tempfile.mkstemp(suffix=".txt")
    os.close(fd)

    args = [
        str(exe), url,
        "-f", format_id,
        # Обрізаємо саме назву відео, а не весь шлях: --trim-filenames ріже
        # рядок цілком і файл може лягти не в ту папку.
        "-o", str(output_dir / "%(title).120B.%(ext)s"),
        "--merge-output-format", "mp4",
        "--windows-filenames",
        "--no-playlist",
        "--no-warnings",
        "--newline",
        "--progress-template", "PROG|%(progress.status)s|%(progress._percent_str)s|%(progress._speed_str)s",
        "--print-to-file", "after_move:filepath", result_file,
    ]
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        args += ["--ffmpeg-location", str(ffmpeg)]

    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )

    for line in process.stdout:
        line = line.strip()
        if not line.startswith("PROG|") or progress_callback is None:
            continue
        parts = line.split("|")
        status = parts[1] if len(parts) > 1 else ""
        percent_raw = parts[2] if len(parts) > 2 else ""
        speed = (parts[3] if len(parts) > 3 else "").strip()
        match = _PERCENT.search(percent_raw)
        percent = float(match.group(1)) if match else 0.0
        if status == "finished":
            progress_callback(100.0, "Обробка (конвертація/об'єднання)...")
        else:
            suffix = f" ({speed})" if speed and speed != "Unknown" else ""
            progress_callback(percent, f"Завантаження... {percent:.1f}%{suffix}")

    stderr = process.stderr.read()
    process.wait()

    try:
        path_text = Path(result_file).read_text(encoding="utf-8", errors="replace").strip()
    finally:
        Path(result_file).unlink(missing_ok=True)

    if process.returncode != 0:
        raise DownloaderError("Помилка завантаження: " + _last_error(stderr))

    final = path_text.splitlines()[-1].strip() if path_text else ""
    if final and Path(final).exists():
        return Path(final)

    # Запасний варіант: найсвіжіший файл у папці призначення.
    files = sorted(output_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if files:
        return files[0]
    raise DownloaderError("Завантаження завершилось, але файл не знайдено.")
