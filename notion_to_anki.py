#!/usr/bin/env python3
"""Convert a Notion HTML export with toggle blocks into an Anki APKG deck."""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag


FIELD_SEPARATOR = "\x1f"
MODEL_NAME = "Notion Toggle Basic Centered"
MODEL_ID_SEED = "model:notion-toggle-basic:antiarrhythmika-design-v7-category-label"
DEFAULT_CARD_COLOR = "#4f8f87"
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
CSS = """
.card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  font-size: 19px;
  line-height: 1.48;
  text-align: left;
  color: #243043;
  background: #eef2f7;
  margin: 0;
  padding: 20px;
}
.card-theme {
  --accent: #4f8f87;
  max-width: 760px;
  margin: 0 auto;
  background: #ffffff;
  border-radius: 18px;
  box-shadow: 0 8px 28px rgba(23, 35, 58, 0.12);
  overflow: hidden;
  padding: 0 24px 24px;
  border: 1px solid rgba(0, 0, 0, 0.06);
}
.topbar {
  height: 9px;
  background: var(--accent);
  margin: 0 -24px 18px;
}
.badge {
  display: inline-block;
  padding: 6px 11px;
  border-radius: 999px;
  color: var(--accent);
  border: 1px solid var(--accent);
  font-weight: 750;
  font-size: 13px;
  letter-spacing: .02em;
  margin-bottom: 16px;
}
.label {
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .13em;
  margin-bottom: 7px;
}
.question {
  font-size: 25px;
  font-weight: 750;
  line-height: 1.32;
  color: #172033;
}
.question.compact {
  font-size: 19px;
  font-weight: 650;
}
.hint {
  margin-top: 28px;
  color: #8490a3;
  font-size: 13px;
  text-align: center;
}
.front, .back { color: inherit; }
.answer { color: #273449; }
.answer b { color: var(--accent); }
.answer a { color: var(--accent); }
.answer ul, .answer ol { padding-left: 1.25em; margin: .55em 0; }
.answer li { margin: .34em 0; }
.answer code, .answer pre { background: #eef2f5; color: #17212b; border-radius: 6px; }
.answer code { padding: .1em .25em; }
.answer pre { overflow-x: auto; padding: .8em 1em; }
.answer img {
  display: block;
  width: auto !important;
  max-width: 100% !important;
  max-height: 58vh !important;
  height: auto !important;
  object-fit: contain;
  margin: 12px auto 5px;
  padding: 6px;
  box-sizing: border-box;
  border: 1px solid #d9e0ea;
  border-radius: 12px;
  background: #fff;
}
#answer {
  border: 0;
  height: 1px;
  background: #dfe5ee;
  margin: 22px 0;
}
.nightMode.card, .card.nightMode { color: #e8edf6; background: #121722; }
.nightMode .card-theme, .card.nightMode .card-theme { background: #1c2432; border-color: #303b4d; box-shadow: none; }
.nightMode .question, .card.nightMode .question { color: #f5f7fb; }
.nightMode .answer, .card.nightMode .answer { color: #e1e7f0; }
.nightMode #answer, .card.nightMode #answer { background: #394456; }
.nightMode .badge, .card.nightMode .badge { background: rgba(255,255,255,.06); }
.nightMode .answer code, .nightMode .answer pre { background: #252e38; color: #f0f3f7; }
sub, sup { line-height: 0; }
@media (max-width: 640px) {
  .card { padding: 10px; }
  .card-theme { padding: 0 16px 18px; }
  .topbar { margin-left: -16px; margin-right: -16px; }
  .question { font-size: 22px; }
  .question.compact { font-size: 18px; }
  .answer img { max-height: 48vh !important; }
}
""".strip()

QFMT = '''<div class="card-theme" style="--accent: {{Color}};">
  <div class="topbar"></div>
  <div class="badge">{{CategoryLabel}}</div>
  <div class="label">FRAGE</div>
  <div class="question">{{Front}}</div>
  <div class="hint">Antwort anzeigen</div>
</div>'''

AFMT = '''<div class="card-theme" style="--accent: {{Color}};">
  <div class="topbar"></div>
  <div class="badge">{{CategoryLabel}}</div>
  <div class="label">FRAGE</div>
  <div class="question compact">{{Front}}</div>
  <hr id="answer">
  <div class="label">ANTWORT</div>
  <div class="answer">{{Back}}</div>
</div>'''


@dataclass
class MediaRef:
    source: Path
    name: str


@dataclass
class CardData:
    front: str
    back: str
    source_id: str | None = None
    color: str = DEFAULT_CARD_COLOR
    category_label: str = ""
    heading_category: str = ""


def normalize_color(value: str | None, fallback: str = DEFAULT_CARD_COLOR) -> str:
    """Return a CSS-safe, normalized six-digit hex color."""
    if value and COLOR_RE.fullmatch(value.strip()):
        return value.strip().lower()
    return fallback


@dataclass
class ConversionResult:
    output_path: Path
    deck_name: str
    notes: int
    cards: int
    media_files: int
    used_genanki: bool
    missing_media: list[str]


class MediaResolver:
    def __init__(self, html_path: Path, media_dir: Path | None) -> None:
        self.html_dir = html_path.parent
        self.media_dir = media_dir
        self._by_source: dict[Path, MediaRef] = {}
        self._used_names: dict[str, Path] = {}
        self.missing: list[str] = []

    @property
    def media(self) -> list[MediaRef]:
        return sorted(self._by_source.values(), key=lambda item: item.name.lower())

    def rewrite_url(self, value: str | None) -> str | None:
        if not value:
            return value

        parsed = urlparse(value)
        if parsed.scheme in {"http", "https", "mailto", "data"}:
            return value

        source = self._resolve_local_file(parsed.path)
        if source is None:
            self.missing.append(value)
            return value

        return self._register(source).name

    def _resolve_local_file(self, raw_path: str) -> Path | None:
        decoded = unquote(raw_path).replace("/", os.sep)
        candidates = [
            self.html_dir / decoded,
            self.html_dir / Path(decoded).name,
        ]
        if self.media_dir is not None:
            candidates.extend(
                [
                    self.media_dir / decoded,
                    self.media_dir / Path(decoded).name,
                ]
            )

        for candidate in candidates:
            candidate = candidate.resolve()
            if candidate.is_file():
                return candidate
        return None

    def _register(self, source: Path) -> MediaRef:
        source = source.resolve()
        if source in self._by_source:
            return self._by_source[source]

        desired = safe_media_name(source.name)
        media_name = desired
        stem = Path(desired).stem
        suffix = Path(desired).suffix
        counter = 2
        while media_name in self._used_names and self._used_names[media_name] != source:
            media_name = f"{stem}_{counter}{suffix}"
            counter += 1

        ref = MediaRef(source=source, name=media_name)
        self._by_source[source] = ref
        self._used_names[media_name] = source
        return ref


def safe_media_name(name: str) -> str:
    """Keep Anki media names simple while preserving readable filenames."""
    cleaned = re.sub(r'[\\/:*?"<>|#%\x00-\x1f]', "_", name).strip()
    return cleaned or hashlib.sha1(name.encode("utf-8")).hexdigest()


def deterministic_id(seed: str, minimum: int = 1_000_000_000) -> int:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return minimum + (int(digest[:12], 16) % 8_000_000_000_000)


def detect_html_file(directory: Path) -> Path:
    html_files = sorted(directory.glob("*.html"))
    if len(html_files) != 1:
        names = ", ".join(path.name for path in html_files) or "none"
        raise SystemExit(
            "Pass an HTML file explicitly. "
            f"Auto-detection expected exactly one .html file, found: {names}"
        )
    return html_files[0]


def detect_media_dir(html_path: Path, soup: BeautifulSoup) -> Path | None:
    candidates: list[Path] = []
    for element in soup.find_all(["img", "a"]):
        attr = "src" if element.name == "img" else "href"
        value = element.get(attr)
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https", "mailto", "data"}:
            continue
        decoded = unquote(parsed.path).replace("/", os.sep)
        parts = Path(decoded).parts
        if len(parts) > 1:
            candidates.append(html_path.parent / parts[0])

    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def extract_cards(
    soup: BeautifulSoup,
    resolver: MediaResolver,
    *,
    include_nested_toggles: bool = False,
) -> list[CardData]:
    cards: list[CardData] = []
    headings_by_details = collect_heading_categories(soup)
    for details in soup.find_all("details"):
        if not include_nested_toggles and details.find_parent("details") is not None:
            continue

        summary = details.find("summary", recursive=False)
        if summary is None:
            continue

        front = clean_fragment(summary.contents, resolver, front=True)
        back_nodes = [
            child
            for child in details.contents
            if not (isinstance(child, Tag) and child.name == "summary")
        ]
        back = clean_fragment(back_nodes, resolver, front=False)

        if text_content(front) or text_content(back) or "<img" in back:
            cards.append(
                CardData(
                    front=front,
                    back=back,
                    source_id=details.get("id"),
                    heading_category=headings_by_details.get(id(details), ""),
                )
            )
    return cards


def collect_heading_categories(soup: BeautifulSoup) -> dict[int, str]:
    """Map each toggle to the closest active Notion h1/h2/h3/h4 heading above it."""
    headings: dict[int, str] = {}
    active: dict[int, str] = {}
    for element in soup.find_all(["h1", "h2", "h3", "h4", "details"]):
        if element.name in {"h1", "h2", "h3", "h4"}:
            if element.find_parent("details") is not None:
                continue
            level = int(element.name[1])
            label = text_content(str(element)).strip()
            if label:
                active[level] = label
            for stale_level in [candidate for candidate in active if candidate > level]:
                del active[stale_level]
            continue

        closest_level = max(active, default=0)
        if closest_level:
            headings[id(element)] = active[closest_level]
    return headings


def clean_fragment(
    nodes: Iterable[Tag | NavigableString],
    resolver: MediaResolver,
    *,
    front: bool,
) -> str:
    fragment = BeautifulSoup("<div></div>", "html.parser")
    container = fragment.div
    assert container is not None
    for node in nodes:
        container.append(copy.deepcopy(node))

    for summary in container.find_all("summary"):
        summary["class"] = clean_class(summary.get("class"), add="nested-toggle-title")

    for element in container.find_all(True):
        if element.name in {"script", "style"}:
            element.decompose()
            continue
        for attr in ["id", "data-token-index"]:
            element.attrs.pop(attr, None)
        if element.name == "img":
            rewritten = resolver.rewrite_url(element.get("src"))
            if rewritten:
                element["src"] = rewritten
            element["loading"] = "lazy"
            element["style"] = merge_image_style(element.get("style"))
        elif element.name == "a":
            rewritten = resolver.rewrite_url(element.get("href"))
            if rewritten:
                element["href"] = rewritten

    wrapper_class = "front" if front else "back"
    body = "".join(str(child) for child in container.contents).strip()
    return f'<div class="{wrapper_class}">{body}</div>'


def clean_class(value: object, *, add: str) -> list[str]:
    classes: list[str] = []
    if isinstance(value, list):
        classes = [str(item) for item in value]
    elif isinstance(value, str):
        classes = value.split()
    if add not in classes:
        classes.append(add)
    return classes


def merge_image_style(style: str | None) -> str:
    blocked = {"width", "max-width", "min-width", "height", "max-height", "min-height"}
    parts = []
    for part in (style or "").split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        key = part.split(":", 1)[0].strip().lower()
        if key not in blocked:
            parts.append(part)
    parts.extend(["width:auto", "max-width:100%", "max-height:58vh", "height:auto"])
    return ";".join(parts)


def text_content(markup: str) -> str:
    return BeautifulSoup(markup, "html.parser").get_text(" ", strip=True)


def sanitize_field(value: str) -> str:
    return value.replace(FIELD_SEPARATOR, " ").strip()


def write_with_genanki(
    cards: list[CardData],
    media: list[MediaRef],
    deck_name: str,
    output_path: Path,
    deck_id: int,
    model_id: int,
) -> bool:
    try:
        import genanki  # type: ignore
    except ImportError:
        return False

    temp_dir = Path(tempfile.mkdtemp(prefix="notion-to-anki-media-"))
    try:
        media_files: list[str] = []
        for item in media:
            target = temp_dir / item.name
            shutil.copy2(item.source, target)
            media_files.append(str(target))

        model = genanki.Model(
            model_id,
            MODEL_NAME,
            fields=[
                {"name": "Front"},
                {"name": "Back"},
                {"name": "Color"},
                {"name": "DeckTitle"},
                {"name": "CategoryLabel"},
            ],
            templates=[
                {
                    "name": "Card 1",
                    "qfmt": QFMT,
                    "afmt": AFMT,
                }
            ],
            css=CSS,
        )
        deck = genanki.Deck(deck_id, deck_name)
        for card in cards:
            deck.add_note(
                genanki.Note(
                    model=model,
                    fields=[card.front, card.back, card.color, deck_name, card.category_label or deck_name],
                )
            )

        package = genanki.Package(deck)
        package.media_files = media_files
        package.write_to_file(str(output_path))
        return True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def write_builtin_apkg(
    cards: list[CardData],
    media: list[MediaRef],
    deck_name: str,
    output_path: Path,
    deck_id: int,
    model_id: int,
) -> None:
    now = int(time.time())
    base_id = int(time.time() * 1000)

    with tempfile.TemporaryDirectory(prefix="notion-to-anki-") as temp_name:
        temp_dir = Path(temp_name)
        db_path = temp_dir / "collection.anki2"
        conn = sqlite3.connect(db_path)
        try:
            create_schema(conn)
            insert_collection(conn, deck_name, deck_id, model_id, now)
            insert_cards(conn, cards, deck_name, deck_id, model_id, now, base_id)
            conn.commit()
        finally:
            conn.close()

        media_map = {str(index): item.name for index, item in enumerate(media)}
        media_path = temp_dir / "media"
        media_path.write_text(json.dumps(media_map, ensure_ascii=False), encoding="utf-8")

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(db_path, "collection.anki2")
            archive.write(media_path, "media")
            for index, item in enumerate(media):
                archive.write(item.source, str(index))


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE col (
            id integer primary key,
            crt integer not null,
            mod integer not null,
            scm integer not null,
            ver integer not null,
            dty integer not null,
            usn integer not null,
            ls integer not null,
            conf text not null,
            models text not null,
            decks text not null,
            dconf text not null,
            tags text not null
        );
        CREATE TABLE notes (
            id integer primary key,
            guid text not null,
            mid integer not null,
            mod integer not null,
            usn integer not null,
            tags text not null,
            flds text not null,
            sfld integer not null,
            csum integer not null,
            flags integer not null,
            data text not null
        );
        CREATE TABLE cards (
            id integer primary key,
            nid integer not null,
            did integer not null,
            ord integer not null,
            mod integer not null,
            usn integer not null,
            type integer not null,
            queue integer not null,
            due integer not null,
            ivl integer not null,
            factor integer not null,
            reps integer not null,
            lapses integer not null,
            left integer not null,
            odue integer not null,
            odid integer not null,
            flags integer not null,
            data text not null
        );
        CREATE TABLE revlog (
            id integer primary key,
            cid integer not null,
            usn integer not null,
            ease integer not null,
            ivl integer not null,
            lastIvl integer not null,
            factor integer not null,
            time integer not null,
            type integer not null
        );
        CREATE TABLE graves (
            usn integer not null,
            oid integer not null,
            type integer not null
        );
        CREATE INDEX ix_notes_usn on notes (usn);
        CREATE INDEX ix_cards_usn on cards (usn);
        CREATE INDEX ix_revlog_usn on revlog (usn);
        CREATE INDEX ix_cards_nid on cards (nid);
        CREATE INDEX ix_cards_sched on cards (did, queue, due);
        CREATE INDEX ix_revlog_cid on revlog (cid);
        CREATE INDEX ix_notes_csum on notes (csum);
        """
    )


def insert_collection(
    conn: sqlite3.Connection,
    deck_name: str,
    deck_id: int,
    model_id: int,
    now: int,
) -> None:
    conf = {
        "activeDecks": [deck_id],
        "curDeck": deck_id,
        "newSpread": 0,
        "nextPos": 1,
        "sortBackwards": False,
        "sortType": "noteFld",
        "timeLim": 0,
        "estTimes": True,
    }
    decks = {
        "1": {
            "id": 1,
            "name": "Default",
            "desc": "",
            "dyn": 0,
            "conf": 1,
            "usn": -1,
            "mod": now,
            "collapsed": False,
            "browserCollapsed": False,
            "newToday": [0, 0],
            "revToday": [0, 0],
            "lrnToday": [0, 0],
            "timeToday": [0, 0],
        },
        str(deck_id): {
            "id": deck_id,
            "name": deck_name,
            "desc": "",
            "dyn": 0,
            "conf": 1,
            "usn": -1,
            "mod": now,
            "collapsed": False,
            "browserCollapsed": False,
            "newToday": [0, 0],
            "revToday": [0, 0],
            "lrnToday": [0, 0],
            "timeToday": [0, 0],
        },
    }
    dconf = {
        "1": {
            "id": 1,
            "name": "Default",
            "mod": now,
            "usn": -1,
            "maxTaken": 60,
            "autoplay": True,
            "timer": 0,
            "replayq": True,
            "new": {
                "bury": True,
                "delays": [1, 10],
                "initialFactor": 2500,
                "ints": [1, 4, 0],
                "order": 1,
                "perDay": 20,
            },
            "rev": {
                "bury": True,
                "ease4": 1.3,
                "fuzz": 0.05,
                "ivlFct": 1,
                "maxIvl": 36500,
                "minSpace": 1,
                "perDay": 200,
            },
            "lapse": {
                "delays": [10],
                "leechAction": 0,
                "leechFails": 8,
                "minInt": 1,
                "mult": 0,
            },
        }
    }
    models = {
        str(model_id): {
            "id": model_id,
            "name": MODEL_NAME,
            "type": 0,
            "mod": now,
            "usn": -1,
            "sortf": 0,
            "did": deck_id,
            "css": CSS,
            "latexPre": "",
            "latexPost": "",
            "flds": [
                field_def("Front", 0),
                field_def("Back", 1),
                field_def("Color", 2),
                field_def("DeckTitle", 3),
                field_def("CategoryLabel", 4),
            ],
            "tmpls": [
                {
                    "name": "Card 1",
                    "ord": 0,
                    "qfmt": QFMT,
                    "afmt": AFMT,
                    "did": None,
                    "bqfmt": "",
                    "bafmt": "",
                }
            ],
            "req": [[0, "all", [0]]],
        }
    }
    conn.execute(
        "insert into col values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            now,
            now,
            now * 1000,
            11,
            0,
            -1,
            0,
            json.dumps(conf),
            json.dumps(models),
            json.dumps(decks),
            json.dumps(dconf),
            json.dumps({}),
        ),
    )


def field_def(name: str, ord_value: int) -> dict[str, object]:
    return {
        "name": name,
        "ord": ord_value,
        "sticky": False,
        "rtl": False,
        "font": "Arial",
        "size": 20,
        "media": [],
    }


def insert_cards(
    conn: sqlite3.Connection,
    cards: list[CardData],
    deck_name: str,
    deck_id: int,
    model_id: int,
    now: int,
    base_id: int,
) -> None:
    for index, card in enumerate(cards, start=1):
        note_id = base_id + index
        card_id = base_id + 100_000 + index
        front_text = text_content(card.front)
        note_guid = hashlib.sha1(
            f"{card.front}\n{card.back}\n{index}".encode("utf-8")
        ).hexdigest()[:10]
        conn.execute(
            "insert into notes values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                note_id,
                note_guid,
                model_id,
                now,
                -1,
                "",
                FIELD_SEPARATOR.join(
                    [card.front, card.back, card.color, deck_name, card.category_label or deck_name]
                ),
                front_text,
                checksum(front_text),
                0,
                "",
            ),
        )
        conn.execute(
            "insert into cards values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                card_id,
                note_id,
                deck_id,
                0,
                now,
                -1,
                0,
                0,
                index,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                "",
            ),
        )


def checksum(value: str) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:8], 16)


def validate_apkg(path: Path) -> tuple[int, int]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "collection.anki2" not in names or "media" not in names:
            raise RuntimeError("APKG is missing collection.anki2 or media manifest.")
        with tempfile.TemporaryDirectory(prefix="notion-to-anki-check-") as temp_name:
            archive.extract("collection.anki2", temp_name)
            conn = sqlite3.connect(Path(temp_name) / "collection.anki2")
            try:
                integrity = conn.execute("pragma integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise RuntimeError(f"SQLite integrity check failed: {integrity}")
                notes = conn.execute("select count(*) from notes").fetchone()[0]
                cards = conn.execute("select count(*) from cards").fetchone()[0]
            finally:
                conn.close()
    return int(notes), int(cards)


def convert_html_export(
    html_path: Path,
    output_path: Path,
    *,
    media_dir: Path | None = None,
    deck_name: str | None = None,
    use_genanki: bool = True,
    include_nested_toggles: bool = False,
    global_color: str = DEFAULT_CARD_COLOR,
    card_colors: dict[int, str] | None = None,
    card_categories: dict[int, str] | None = None,
) -> ConversionResult:
    html_path = html_path.resolve()
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    detected_media_dir = media_dir.resolve() if media_dir else detect_media_dir(html_path, soup)
    final_deck_name = deck_name or (soup.title.get_text(strip=True) if soup.title else html_path.stem)
    output_path = output_path.resolve()

    resolver = MediaResolver(html_path, detected_media_dir)
    cards = extract_cards(
        soup,
        resolver,
        include_nested_toggles=include_nested_toggles,
    )
    if not cards:
        raise ValueError("No Notion toggle blocks were found.")

    global_color = normalize_color(global_color)
    card_colors = card_colors or {}
    card_categories = card_categories or {}
    for index, card in enumerate(cards):
        card.color = normalize_color(card_colors.get(index), global_color)
        card.category_label = sanitize_field(card_categories.get(index) or final_deck_name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    deck_id = deterministic_id(f"deck:{final_deck_name}")
    model_id = deterministic_id(MODEL_ID_SEED)
    used_genanki = False
    if use_genanki:
        used_genanki = write_with_genanki(
            cards, resolver.media, final_deck_name, output_path, deck_id, model_id
        )
    if not used_genanki:
        write_builtin_apkg(cards, resolver.media, final_deck_name, output_path, deck_id, model_id)

    notes, anki_cards = validate_apkg(output_path)
    return ConversionResult(
        output_path=output_path,
        deck_name=final_deck_name,
        notes=notes,
        cards=anki_cards,
        media_files=len(resolver.media),
        used_genanki=used_genanki,
        missing_media=sorted(set(resolver.missing)),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Notion toggle blocks from an HTML export to an Anki APKG deck."
    )
    parser.add_argument(
        "html",
        nargs="?",
        type=Path,
        help="Path to the Notion HTML export. If omitted, auto-detects a single .html file.",
    )
    parser.add_argument(
        "--media-dir",
        type=Path,
        help="Folder containing exported Notion media. Auto-detected from image links if omitted.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .apkg path. Defaults to the deck name in the current folder.",
    )
    parser.add_argument(
        "--deck-name",
        help="Anki deck name. Defaults to the Notion page title.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report what would be generated without writing an APKG.",
    )
    parser.add_argument(
        "--no-genanki",
        action="store_true",
        help="Use the built-in APKG writer even if genanki is installed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    html_path = (args.html or detect_html_file(Path.cwd())).resolve()
    if not html_path.is_file():
        raise SystemExit(f"HTML file not found: {html_path}")

    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    media_dir = (args.media_dir.resolve() if args.media_dir else detect_media_dir(html_path, soup))
    deck_name = args.deck_name or (soup.title.get_text(strip=True) if soup.title else html_path.stem)
    output_path = (args.output or Path.cwd() / f"{safe_filename(deck_name)}.apkg").resolve()

    resolver = MediaResolver(html_path, media_dir)
    cards = extract_cards(soup, resolver)
    if not cards:
        raise SystemExit("No Notion toggle blocks were found.")

    if args.dry_run:
        print(f"HTML: {html_path}")
        print(f"Media folder: {media_dir or 'not detected'}")
        print(f"Deck name: {deck_name}")
        print(f"Cards: {len(cards)}")
        print(f"Media files: {len(resolver.media)}")
        if resolver.missing:
            print(f"Missing local media references: {len(set(resolver.missing))}")
        print("First cards:")
        for card in cards[:5]:
            print(f"- {html.unescape(text_content(card.front))}")
        return 0

    result = convert_html_export(
        html_path,
        output_path,
        media_dir=args.media_dir,
        deck_name=args.deck_name,
        use_genanki=not args.no_genanki,
    )
    print(f"Wrote: {result.output_path}")
    print(f"Deck: {result.deck_name}")
    print(f"Cards: {result.cards} ({result.notes} notes)")
    print(f"Media files: {result.media_files}")
    print(f"Writer: {'genanki' if result.used_genanki else 'built-in'}")
    if result.missing_media:
        print(f"Warning: {len(result.missing_media)} local media references could not be resolved.")
    return 0


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|#%\x00-\x1f]', "_", value).strip(" .")
    return cleaned or "notion-deck"


if __name__ == "__main__":
    raise SystemExit(main())
