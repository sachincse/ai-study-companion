# Tutorial video

The full narrated tutorial is generated from this folder, so it can be rebuilt
whenever the app changes. Nothing is edited by hand.

| File | What it is |
|---|---|
| `script.yaml` | The narration, split into scenes and beats, plus what happens on screen during each beat |
| `slides.html` | The explainer slides (intro, how it works, backend deep dive, benchmarks) |
| `terminal.html` | A terminal and editor used for the "run it from GitHub" part |
| `terminal_output.json` | Real console output captured from a fresh clone, install and first start |
| `browser.html` | A browser frame that hosts the running app at 1.25x scale, with a visible cursor |
| `make_tutorial.py` | Synthesises the voice, records every scene, and assembles the MP4 |

## Build it

```bash
pip install -r scripts/tutorial/requirements.txt
playwright install chromium
# ffmpeg with libx264 on PATH (the assemble stage needs it):
#   winget install Gyan.FFmpeg  |  brew install ffmpeg  |  sudo apt install ffmpeg
# Kokoro voice files (about 350 MB): kokoro-v1.0.onnx and voices-v1.0.bin from
# https://github.com/thewh1teagle/kokoro-onnx/releases, in one folder

# the app must be running: backend on :8000 (with a Gemini key in .env) and Vite on :5173
python scripts/fetch_open_notes.py
python scripts/tutorial/make_tutorial.py all --kokoro-dir path/to/kokoro --preview-720
```

Stages can run one at a time (`tts`, `record`, `assemble`, `qa`), and `--only s16-quiz`
re-records a single scene. Waits on the model are recorded in real time and sped up
in the edit, with a fast-forward badge, so the narration never talks over a spinner.
The output lands in `build/tutorial/out/`: the MP4 with chapters and soft subtitles,
an `.srt` file, `chapters.md` and a contact sheet for review.
