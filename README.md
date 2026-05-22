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
- [ ] Phase 1 — Data layer (CSV, state, trash)
- [ ] Phase 2 — Logic engine (pipeline, retry, error handling, queue)
- [ ] Phase 3 — AI connectors
- [ ] Phase 4 — FastAPI backend
- [ ] Phase 5 — HTML frontend
- [ ] Phase 6 — Video compilation
- [ ] Phase 7 — Manual upload export
- [ ] Phase 8 — YouTube API automation
