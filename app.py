#!/usr/bin/env python3
"""Local web UI for converting Notion HTML ZIP exports into Anki decks."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file
from bs4 import BeautifulSoup

from notion_to_anki import (
    DEFAULT_CARD_COLOR,
    MediaResolver,
    convert_html_export,
    extract_cards,
    normalize_color,
    safe_filename,
    text_content,
)


APP_ROOT = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 750 * 1024 * 1024
MAX_EXTRACTED_BYTES = MAX_UPLOAD_BYTES * 2
MAX_NESTED_ZIP_DEPTH = 4

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/convert")
def convert() -> Response:
    upload = request.files.get("zip_file")
    if upload is None or not upload.filename:
        return error_response("Bitte eine ZIP-Datei auswaehlen.", 400)
    if not upload.filename.lower().endswith(".zip"):
        return error_response("Die Datei muss eine .zip-Datei sein.", 400)

    deck_name = (request.form.get("deck_name") or "").strip() or None
    include_nested_toggles = request.form.get("include_nested_toggles") == "on"
    global_color = normalize_color(request.form.get("global_color"), DEFAULT_CARD_COLOR)
    temp_dir = Path(tempfile.mkdtemp(prefix="notion-web-upload-"))
    zip_path = temp_dir / "upload.zip"
    extract_dir = temp_dir / "extracted"
    output_dir = temp_dir / "output"
    extract_dir.mkdir()
    output_dir.mkdir()

    try:
        card_colors = parse_card_colors(request.form.get("card_colors"))
        card_categories = parse_card_categories(request.form.get("card_categories"))
        upload.save(zip_path)
        extract_export_zip(zip_path, extract_dir)
        html_path = find_single_html_file(extract_dir)
        final_name = deck_name or html_path.stem
        output_path = output_dir / f"{safe_filename(final_name)}.apkg"
        result = convert_html_export(
            html_path,
            output_path,
            deck_name=deck_name,
            use_genanki=True,
            include_nested_toggles=include_nested_toggles,
            global_color=global_color,
            card_colors=card_colors,
            card_categories=card_categories,
        )
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return error_response(str(exc), 400)

    download_name = f"{safe_filename(result.deck_name)}.apkg"
    response = send_file(
        result.output_path,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/octet-stream",
    )

    @response.call_on_close
    def cleanup() -> None:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return response


@app.post("/preview")
def preview() -> Response:
    """Parse the upload without persisting it and return card fronts for editing."""
    upload = request.files.get("zip_file")
    if upload is None or not upload.filename or not upload.filename.lower().endswith(".zip"):
        return jsonify({"error": "Bitte eine ZIP-Datei auswählen."}), 400

    temp_dir = Path(tempfile.mkdtemp(prefix="notion-web-preview-"))
    try:
        zip_path = temp_dir / "upload.zip"
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        upload.save(zip_path)
        extract_export_zip(zip_path, extract_dir)
        html_path = find_single_html_file(extract_dir)
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        resolver = MediaResolver(html_path, None)
        cards = extract_cards(
            soup,
            resolver,
            include_nested_toggles=request.form.get("include_nested_toggles") == "on",
        )
        return jsonify({"cards": [{"index": i, "front": text_content(card.front)} for i, card in enumerate(cards)]})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def parse_card_colors(raw_value: str | None) -> dict[int, str]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("Ungültige Kartenfarben.")
    if not isinstance(payload, dict):
        raise ValueError("Ungültige Kartenfarben.")
    result: dict[int, str] = {}
    for raw_index, raw_color in payload.items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if index >= 0 and isinstance(raw_color, str):
            normalized = normalize_color(raw_color, "")
            if normalized:
                result[index] = normalized
    return result


def parse_card_categories(raw_value: str | None) -> dict[int, str]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("Ungültige Kartenkategorien.")
    if not isinstance(payload, dict):
        raise ValueError("Ungültige Kartenkategorien.")
    result: dict[int, str] = {}
    for raw_index, raw_label in payload.items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if index >= 0 and isinstance(raw_label, str):
            label = raw_label.strip()
            if label:
                result[index] = label[:80]
    return result


def extract_export_zip(zip_path: Path, target_dir: Path) -> None:
    extracted_bytes = safe_extract_zip(zip_path, target_dir)
    processed = {zip_path.resolve()}

    for _depth in range(MAX_NESTED_ZIP_DEPTH):
        nested_zips = [
            path
            for path in sorted(target_dir.rglob("*.zip"))
            if path.is_file() and path.resolve() not in processed
        ]
        if not nested_zips:
            return

        for nested_zip in nested_zips:
            nested_target = unique_extract_dir(nested_zip)
            nested_target.mkdir(parents=True, exist_ok=False)
            extracted_bytes += safe_extract_zip(nested_zip, nested_target)
            processed.add(nested_zip.resolve())
            if extracted_bytes > MAX_EXTRACTED_BYTES:
                raise ValueError("Die entpackten Dateien sind zu gross.")

        if any(target_dir.rglob("*.html")):
            return

    raise ValueError("Die ZIP-Datei ist zu tief verschachtelt.")


def unique_extract_dir(zip_path: Path) -> Path:
    base = zip_path.with_name(f"{safe_filename(zip_path.stem)}_unzipped")
    candidate = base
    counter = 2
    while candidate.exists():
        candidate = zip_path.with_name(f"{base.name}_{counter}")
        counter += 1
    return candidate


def safe_extract_zip(zip_path: Path, target_dir: Path) -> int:
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if not infos:
            raise ValueError("Die ZIP-Datei ist leer.")

        total_size = sum(info.file_size for info in infos)
        if total_size > MAX_EXTRACTED_BYTES:
            raise ValueError("Die entpackten Dateien sind zu gross.")

        for info in archive.infolist():
            destination = (target_root / info.filename).resolve()
            try:
                destination.relative_to(target_root)
            except ValueError:
                raise ValueError("Unsicherer Pfad in der ZIP-Datei.")
            archive.extract(info, target_root)
    return total_size


def find_single_html_file(directory: Path) -> Path:
    html_files = sorted(path for path in directory.rglob("*.html") if path.is_file())
    if not html_files:
        raise ValueError("In der ZIP-Datei wurde keine Notion-HTML-Datei gefunden.")
    if len(html_files) > 1:
        names = ", ".join(path.name for path in html_files[:5])
        raise ValueError(
            "Die ZIP-Datei enthaelt mehrere HTML-Dateien. "
            f"Bitte nur einen Notion-Export hochladen. Gefunden: {names}"
        )
    return html_files[0]


def error_response(message: str, status: int) -> tuple[str, int]:
    return render_template("index.html", error=message), status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local Notion-to-Anki web UI.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 10000)))
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
