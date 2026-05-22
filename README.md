# AI-Assisted Video Content Channel

A local pipeline application for producing AI-assisted video content for
YouTube and short-form platforms. Combines script generation, image creation,
animation, voiceover, and music into a single managed workflow with a
browser-based UI for review and approval at each stage.

---

## Tech Stack

| Role | Tool |
|---|---|
| Scriptwriting | Claude API (Anthropic) |
| Image generation | Flux (local via ComfyUI) |
| Animation | Kling API (Runway as fallback) |
| Voiceover | ElevenLabs API |
| Music | Suno API |
| Backend | Python / FastAPI |
| Frontend | HTML / CSS / Vanilla JS |
| Video assembly | MoviePy |

---

## Requirements

- Python 3.11+
- ComfyUI running locally (for Flux image generation)
- API keys for: Anthropic, ElevenLabs, Kling, Suno
- (Future) Google Cloud project with YouTube Data API v3 enabled

---

## Setup

### 1. Clone the repo
```bash
git clone <your-repo-url>
cd <repo-folder>
```

### 2. Run the scaffold script (first time only)
```bash
bash setup.sh
```

### 3. Create and activate virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Fill in your API keys
Edit `.env` with your credentials. Never commit this file.

### 6. Start the application
```bash
python main.py
```

The app will start the FastAPI backend and open the UI in your default browser
at `http://127.0.0.1:8000`.

---

## Project Structure

```
/
├── main.py                  # Entry point
├── .env                     # API keys (never committed)
├── requirements.txt
├── setup.sh                 # First-time scaffold script
│
├── /backend/
│   ├── pipeline.py          # Pipeline orchestration
│   ├── state.py             # Project state management
│   ├── queue_worker.py      # Async update queue
│   ├── trash_manager.py     # Auto-deletion of rejected assets
│   ├── compiler.py          # Video assembly (MoviePy)
│   ├── scraper.py           # Topic research scraper
│   └── /connectors/         # One module per AI engine
│
├── /frontend/               # Browser UI
│
└── /channels/
    /{channel-name}/
        ├── topics.csv
        ├── style_guide.md
        ├── performance-log.csv
        └── /in-production/
            └── /{YYYY-MM_title}/
                ├── script.md
                ├── shot_list.json
                ├── sources.json
                ├── project_state.json
                ├── /assets/
                ├── /trash/
                └── /export/
```

---

## Development Phases

- [x] Phase 0 — Scaffolding
- [x] Phase 1 — Data layer (CSV, state, trash)
- [x] Phase 2 — Logic engine (pipeline, retry, error handling, queue)
- [x] Phase 3 — AI connectors
- [x] Phase 4 — FastAPI backend
- [X] Phase 5 — HTML frontend
- [X] Phase 6 — Video compilation
- [ ] Phase 7 — Manual upload export
- [ ] Phase 8 — YouTube API automation

---

## Managing Channels

Channels are directories under `/channels/`. The app discovers them automatically
by scanning that directory — no config files need updating.

### Renaming a channel

```bash
mv channels/old-name channels/new-name
```

If any projects are currently in-production under that channel, their
`project_state.json` files contain a `"channel"` field that will need updating
to match the new name:

```bash
# Find and update all affected state files
sed -i 's/"channel": "old-name"/"channel": "new-name"/g' \
  channels/new-name/in-production/*/project_state.json
```

If no projects are in-production, the rename is instant.

### Adding a new channel

```bash
mkdir -p channels/new-channel-name/{style_diffs,templates,in-production,published}
touch channels/new-channel-name/topics.csv
touch channels/new-channel-name/style_guide.md
touch channels/new-channel-name/performance-log.csv
```

The homepage channel selector will pick it up automatically on next page load.

### Channel contents

Each channel directory holds:

| File / Folder        | Purpose                                              |
|----------------------|------------------------------------------------------|
| `topics.csv`         | Planned and completed video topics                   |
| `style_guide.md`     | Per-channel tone, structure rules, banned phrases    |
| `performance-log.csv`| CTR, view duration, subscriber conversion per video  |
| `style_diffs/`       | Draft vs final script diffs for style guide updates  |
| `templates/`         | Reusable prompts and shot list templates             |
| `in-production/`     | Active projects                                      |
| `published/`         | Archived projects after upload                       |

### Per-channel configuration (future)

A `channel_config.json` file per channel can be added to store channel-specific
settings such as ElevenLabs voice ID, Flux style preset, or default format.
This is not yet implemented but fits naturally into the existing structure.
