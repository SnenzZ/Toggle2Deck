# Notion Toggle to Anki

Local converter for a Notion HTML export. It turns every Notion toggle block into a
Basic Anki card:

- toggle title -> card front
- toggle body -> card back
- nested toggles -> remain inside parent backs without creating extra cards
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
http://127.0.0.1:10000
```

Upload a `.zip` file that contains exactly one Notion `.html` export and the
matching media folder. Nested ZIP files are supported, for example a ZIP that
contains another ZIP with the actual Notion export inside. The browser downloads
the generated `.apkg` after the conversion.

To use another local port:

```powershell
python app.py --port 8765
```

## Deploy on Render Free

This project is ready for Render as a Python Web Service. The app uses Render's
ephemeral filesystem only for temporary upload extraction and APKG generation;
files are deleted after the download response is closed. Nothing is designed to
be stored permanently on the server.

1. Push this folder to a GitHub repository.
2. In Render, create a new Blueprint from the repository.
3. Render will read `render.yaml` automatically.
4. Deploy the service.

The included `render.yaml` uses:

```yaml
services:
  - type: web
    name: notion-to-anki
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300
```

You can also create the service manually with:

```text
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300
```

Render provides the `PORT` environment variable. Locally, `python app.py`
defaults to port `10000` and host `0.0.0.0`.

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

Required for production deployment:

```powershell
pip install gunicorn
```

Optional:

```powershell
pip install genanki
```

`beautifulsoup4` is used to parse Notion's HTML. `genanki` is optional because
the script can write a valid Anki package by itself.

## Notes

- The parser reads top-level `<details><summary>...</summary>...</details>`
  blocks, which is how Notion exports toggles. Nested toggles stay in the
  parent card body but do not become separate Anki cards.
- Image references such as `media-folder/image%201.png` are resolved from the
  HTML location and the exported media folder.
- Local image names are simplified only when Anki would dislike the original
  filename. The card HTML is rewritten to match the packaged media names.
