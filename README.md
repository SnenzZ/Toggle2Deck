# Notion Toggle to Anki

Local converter for a Notion HTML export. It turns every Notion toggle block into a
Basic Anki card:

- toggle title -> card front
- toggle body -> card back
- nested toggles -> their own cards, while still appearing inside parent backs
- formatting, lists, links, and local images are preserved
- exported media files are bundled into the `.apkg`

The tool prefers `genanki` when it is installed, but also includes a built-in APKG
writer so it can run offline.

## Web app

Start the local upload page:

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:8765
```

Upload a `.zip` file that contains exactly one Notion `.html` export and the
matching media folder. Nested ZIP files are supported, for example a ZIP that
contains another ZIP with the actual Notion export inside. The browser downloads
the generated `.apkg` after the conversion.

## CLI quick start

From this folder:

```powershell
python notion_to_anki.py
```

With the files currently in this directory, that creates:

```text
5. Herzinsuffizienz und KH.apkg
```

Import the `.apkg` file into Anki with `File -> Import`.

## CLI

```powershell
python notion_to_anki.py [HTML_FILE] --media-dir MEDIA_FOLDER --output OUTPUT.apkg --deck-name "Deck name"
```

All arguments are optional when the folder contains one Notion `.html` export and
the media folder can be detected from image links.

Useful commands:

```powershell
# Preview how many cards/media files will be generated
python notion_to_anki.py --dry-run

# Explicit paths
python notion_to_anki.py "5 Herzinsuffizienz und KH 33809585118580a99136c00c1bd2e1d5.html" `
  --media-dir "5 Herzinsuffizienz und KH" `
  --output "herzinsuffizienz.apkg"

# Force the dependency-free writer
python notion_to_anki.py --no-genanki
```

## Dependencies

Required:

```powershell
pip install beautifulsoup4 Flask
```

Optional:

```powershell
pip install genanki
```

`beautifulsoup4` is used to parse Notion's HTML. `genanki` is optional because
the script can write a valid Anki package by itself.

## Notes

- The parser reads every `<details><summary>...</summary>...</details>` block,
  which is how Notion exports toggles.
- Image references such as `media-folder/image%201.png` are resolved from the
  HTML location and the exported media folder.
- Local image names are simplified only when Anki would dislike the original
  filename. The card HTML is rewritten to match the packaged media names.
