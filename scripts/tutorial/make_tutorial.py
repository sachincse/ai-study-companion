#!/usr/bin/env python3
"""Build the narrated tutorial video for AI Study Companion.

Nothing in the video is hand-edited. The narration lives in ``script.yaml``, the
voice is synthesised locally with Kokoro, and every picture is captured from a
real page with Playwright: ``slides.html``, ``terminal.html`` (real console output
from ``terminal_output.json``), the running app inside ``browser.html`` driven
with a real model, and the backend's own ``/api/docs``.

Stages (``all`` runs them in order)::

    tts       synthesise each narration beat (cached by text)
    record    capture every scene; waits on the model are compressed later
    assemble  build the 30 fps timeline, place the narration, add chapters and
              subtitles, encode MP4 (H.264 + AAC) and write an .srt file
    qa        contact sheet of every beat, plus an optional Whisper check

Example::

    python scripts/tutorial/make_tutorial.py all --build build/tutorial --kokoro-dir ~/models/kokoro

Needs the app running locally (backend on :8000, Vite on :5173) with a provider
key in .env for the model chosen in the Settings scene, ffmpeg on PATH, and the
packages in ``scripts/tutorial/requirements.txt``.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import bisect
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
W, H, FPS = 1920, 1080, 30
SR = 24_000
LEAD, GAP, TAIL = 0.6, 0.45, 0.9  # seconds: before the first beat, after each beat, after the last beat
XFADE = 0.45  # cross-fade between scenes
APP = "http://localhost:5173"
API = "http://localhost:8000"
DB_PATH = ROOT / "storage" / "study_companion.db"
BOOK = ROOT / "data" / "sample_notes" / "Database_Design_2nd_Edition_(Watt_Eng)_CC-BY-4.0.pdf"
SHELL = f"{APP}/__tutorial"
# a 2 px corner square that flips between two near-identical colours: forces a repaint so the
# screencast always delivers a frame when a scene starts, even on a static page
TICK_JS = """() => {
  if (window.tick) return true;
  const el = document.createElement('div');
  el.style.cssText = 'position:fixed;left:0;top:0;width:2px;height:2px;z-index:2147483647;pointer-events:none;background:rgb(11,18,32)';
  document.body.appendChild(el);
  let on = false;
  window.tick = () => { on = !on; el.style.background = on ? 'rgb(11,18,33)' : 'rgb(11,18,32)'; return true; };
  return true;
}"""


# ----------------------------------------------------------------------------- script

def load_script() -> dict:
    data = yaml.safe_load((HERE / "script.yaml").read_text(encoding="utf-8"))
    chapter = None
    for scene in data["scenes"]:
        if scene.get("chapter"):
            chapter = scene["chapter"]
            scene["_chapter_start"] = True
        scene["_chapter"] = chapter
    return data


def beat_key(text: str, voice: str, speed: float) -> str:
    return hashlib.sha1(f"{voice}|{speed}|{text}".encode()).hexdigest()[:16]


def spoken(beat: dict) -> str:
    return " ".join(beat["say"].split())


# Subtitles show the written form of what the voice spells out.
WRITTEN = [
    (r"github dot com, slash sachin C S E, slash (?:A I|AI) dash study dash companion", "github.com/sachincse/ai-study-companion"),
    (r"console dot groq dot com", "console.groq.com"),
    (r"A I studio dot google dot com", "aistudio.google.com"),
    (r"dot slash scripts slash dev dot p s one", "./scripts/dev.ps1"),
    (r"dot slash scripts slash dev dot s h", "./scripts/dev.sh"),
    (r"slash (?:A P I|API) slash docs", "/api/docs"),
    (r"localhost, port fifty-one seventy-three", "localhost:5173"),
    (r"localhost, port eight thousand", "localhost:8000"),
    (r"port eight thousand", "port 8000"),
    (r"port fifty-one seventy-three", "port 5173"),
    (r"dot env dot example", ".env.example"),
    (r"\b[Dd]ot env\b", ".env"),
    (r"git ignore", ".gitignore"),
    (r"g s k underscore", "gsk_"),
    (r"Fast A P I", "FastAPI"),
    (r"A P I", "API"),
    (r"A I Z A", "AIza"),
    (r"x A I", "xAI"),
    (r"A K T U", "AKTU"),
    (r"\bA I\b", "AI"),
    (r"B Tech", "B.Tech"),
    (r"P D F", "PDF"),
    (r"J W T", "JWT"),
    (r"S D K", "SDK"),
    (r"S Q Lite", "SQLite"),
    (r"B G E", "BGE"),
    (r"user I D", "user ID"),
    (r"Node J S", "Node.js"),
    (r"\bc p\b", "cp"),
    (r"B C N F", "BCNF"),
    (r"B M twenty-five", "BM25"),
    (r"S M two", "SM-2"),
    (r"G L Bajaj", "GL Bajaj"),
    (r"B crypt", "bcrypt"),
    (r"\brag\b", "RAG"),
    (r"Python three point eleven", "Python 3.11"),
    (r"twenty-two point twelve or newer", "22.12 or newer"),
    (r"Qwen two point five", "Qwen 2.5"),
    (r"sixty-five megabytes", "65 MB"),
    (r"A hundred and fifty-three pages became a hundred and fifty-eight passages", "153 pages became 158 passages"),
    (r"two thousand characters", "2,000 characters"),
    (r"five hundred tokens", "500 tokens"),
    (r"two hundred characters", "200 characters"),
    (r"three hundred and eighty-four numbers", "384 numbers"),
    (r"one over sixty plus its rank", "1 / (60 + its rank)"),
    (r"best six passages", "best 6 passages"),
    (r"two point five", "2.5"),
    (r"one point three", "1.3"),
    (r"one, six, and then fifteen days", "1, 6, and then 15 days"),
    (r"ten minutes", "10 minutes"),
    (r"Fourteen of them", "14 of them"),
    (r"[Ff]ourteen providers", "14 providers"),
    (r"fourteen named providers", "14 named providers"),
    (r"Thirteen of the named providers", "13 of the named providers"),
    (r"[Nn]ineteen tables", "19 tables"),
    (r"[Nn]ineteen database tables", "19 database tables"),
    (r"keys one to four", "keys 1 to 4"),
    (r"Two thousand and sixteen passages", "2,016 passages"),
    (r"thirty-nine", "39"),
    (r"eighty-five percent", "85%"),
    (r"eighty-seven percent", "87%"),
    (r"zero point seven three", "0.73"),
    (r"forty-five milliseconds", "45 ms"),
    (r"four point seven out of five", "4.7 out of 5"),
    (r"Ninety-two percent", "92%"),
    (r"forty-eight automated tests", "48 automated tests"),
    (r"fifty-three automated tests", "53 automated tests"),
    (r"\bC I\b", "CI"),
    (r"\bE R modelling", "E-R modelling"),
    (r"S Q L\b", "SQL"),
]


def written(text: str) -> str:
    for pattern, repl in WRITTEN:
        text = re.sub(pattern, repl, text)
    return text


# ----------------------------------------------------------------------------- tts

def stage_tts(args: argparse.Namespace) -> None:
    import soundfile as sf
    from kokoro_onnx import Kokoro

    script = load_script()
    voice, speed = script["voice"], float(script["speed"])
    kdir = Path(args.kokoro_dir).expanduser()
    kokoro = Kokoro(str(kdir / "kokoro-v1.0.onnx"), str(kdir / "voices-v1.0.bin"))
    adir = args.build / "audio"
    adir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    todo = [(scene, i, beat) for scene in script["scenes"] for i, beat in enumerate(scene["beats"])]
    for n, (scene, i, beat) in enumerate(todo, 1):
        text = spoken(beat)
        wav = adir / f"{beat_key(text, voice, speed)}.wav"
        if not wav.exists():
            samples, sr = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
            samples = _trim(np.asarray(samples, dtype=np.float32), sr)
            sf.write(str(wav), samples, sr, subtype="PCM_16")
            print(f"[tts {n}/{len(todo)}] {scene['id']}#{i}: {len(samples) / sr:.1f}s", flush=True)
        info = sf.info(str(wav))
        manifest[f"{scene['id']}#{i}"] = {"file": wav.name, "duration": round(info.frames / info.samplerate, 3)}
    (args.build / "audio.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total = sum(v["duration"] for v in manifest.values())
    print(f"narration: {len(manifest)} beats, {total / 60:.1f} min of speech")


def _trim(samples: np.ndarray, sr: int, threshold: float = 0.004, pad: float = 0.05) -> np.ndarray:
    idx = np.flatnonzero(np.abs(samples) > threshold)
    if not len(idx):
        return samples
    return samples[max(0, idx[0] - int(pad * sr)): min(len(samples), idx[-1] + int(pad * sr))]


# ----------------------------------------------------------------------------- capture

class SceneFailed(Exception):
    """The scene's footage is unusable (error toast, timeout); it is recorded again."""


class Capture:
    """Chrome screencast -> numbered JPEG frames with wall-clock timestamps."""

    def __init__(self, page: Any, cdp: Any, folder: Path) -> None:
        self.page, self.cdp, self.folder = page, cdp, folder
        self.frames: list[tuple[float, str]] = []
        self.skew: list[float] = []
        self._acks: set = set()

    async def start(self) -> None:
        if self.folder.exists():
            shutil.rmtree(self.folder)
        self.folder.mkdir(parents=True)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1})
        deadline = time.time() + 6
        while not self.frames and time.time() < deadline:  # screencast needs a repaint to emit its first frame
            await self.page.evaluate("() => window.tick && window.tick()")
            await asyncio.sleep(0.1)
        if not self.frames:
            raise SceneFailed("screencast produced no frames")

    def _on_frame(self, params: dict) -> None:
        recv = time.time()
        meta = (params.get("metadata") or {}).get("timestamp")
        ts = meta if meta and abs(recv - meta) < 2 else recv
        self.skew.append(recv - ts)
        name = f"{len(self.frames):06d}.jpg"
        (self.folder / name).write_bytes(base64.b64decode(params["data"]))
        self.frames.append((ts, name))
        task = asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]}))
        self._acks.add(task)
        task.add_done_callback(self._acks.discard)

    async def stop(self) -> None:
        await self.cdp.send("Page.stopScreencast")
        self.cdp.remove_listener("Page.screencastFrame", self._on_frame)
        await asyncio.sleep(0.15)


class Performer:
    """Base for the things a beat can do. Tracks narration end and compressible waits."""

    def __init__(self) -> None:
        self.t0 = 0.0
        self.narration_end = 0.0
        self.warps: list[list[float]] = []
        self.cue: asyncio.Event | None = None  # set by an action when a "when: after" narration may start
        self.beat_start = 0.0
        self.beat_dur = 0.0

    def cue_now(self) -> None:
        if self.cue is not None and not self.cue.is_set():
            self.cue.set()

    async def setup(self, scene: dict, retry: bool) -> None:  # brings the page to the scene's first state (not recorded)
        return None

    async def run(self, scene: dict, beat: dict) -> None:
        raise NotImplementedError

    def compress(self, start: float, end: float, speed: float) -> None:
        """Speed up [start, end] (wall clock) in the edit, but never while the narration is still talking."""
        a, b = max(start, self.narration_end + 0.35), end - 0.45
        if b - a >= 1.2:
            self.warps.append([round(a - self.t0, 3), round(b - self.t0, 3), speed])


async def record_scene(scene: dict, page: Any, cdp: Any, performer: Performer, audio: dict, build: Path, retry: bool) -> None:
    sid = scene["id"]
    await performer.setup(scene, retry)
    cap = Capture(page, cdp, build / "frames" / sid)
    await cap.start()
    t0 = time.time()
    performer.t0, performer.warps, performer.narration_end = t0, [], t0
    beats: list[dict] = []
    await asyncio.sleep(LEAD)
    try:
        for i, beat in enumerate(scene["beats"]):
            dur = audio[f"{sid}#{i}"]["duration"]
            if beat.get("when") == "after":  # narrate once the result is on screen (the action cues it)
                performer.narration_end = time.time()
                performer.cue = asyncio.Event()
                action = asyncio.create_task(performer.run(scene, beat))
                cue = asyncio.create_task(performer.cue.wait())
                await asyncio.wait({action, cue}, return_when=asyncio.FIRST_COMPLETED)
                if not cue.done():
                    cue.cancel()
                if action.done():
                    action.result()  # surface a failure right away
                tb = time.time()
                performer.narration_end = tb + dur
                performer.beat_start, performer.beat_dur = tb, dur
                beats.append({"index": i, "t": round(tb - t0, 3), "duration": dur})
                await action
                performer.cue = None
                rest = tb + dur + GAP - time.time()
                if rest > 0:
                    await asyncio.sleep(rest)
            else:
                tb = time.time()
                performer.narration_end = tb + dur
                performer.beat_start, performer.beat_dur = tb, dur
                beats.append({"index": i, "t": round(tb - t0, 3), "duration": dur})
                await performer.run(scene, beat)
                rest = tb + dur + GAP - time.time()
                if rest > 0:
                    await asyncio.sleep(rest)
        await asyncio.sleep(TAIL)
    finally:
        end = time.time() - t0
        await cap.stop()
    skew = sorted(cap.skew)[len(cap.skew) // 2] if cap.skew else 0.0
    timeline = {
        "id": sid,
        "end": round(end, 3),
        "beats": beats,
        "warps": performer.warps,
        "frames": [[round(ts - t0, 4), name] for ts, name in cap.frames],
        "median_skew": round(skew, 4),
    }
    (build / "timelines").mkdir(parents=True, exist_ok=True)
    (build / "timelines" / f"{sid}.json").write_text(json.dumps(timeline), encoding="utf-8")
    print(f"[record] {sid}: {end:.1f}s raw, {len(cap.frames)} frames, {len(performer.warps)} compressed waits", flush=True)


# ----------------------------------------------------------------------------- slides

class Slides(Performer):
    def __init__(self, page: Any) -> None:
        super().__init__()
        self.page = page

    async def setup(self, scene: dict, retry: bool) -> None:
        await self.page.evaluate("([id]) => show(id, 0)", [scene["slide"]])
        await asyncio.sleep(0.8)

    async def run(self, scene: dict, beat: dict) -> None:
        await self.page.evaluate("([id, step]) => show(id, step)", [scene["slide"], beat.get("step", 0)])


# ----------------------------------------------------------------------------- terminal

TERMINAL_ACTIONS: dict[str, str] = {
    "type_clone": "async (D) => { await T.type('git clone https://github.com/sachincse/ai-study-companion.git'); }",
    "out_clone": "async (D) => { T.enter(); await sleep(450); await T.print(D.clone, 330); T.showPrompt(); }",
    "type_cd": """async (D) => { await T.type('cd ai-study-companion'); T.enter();
        T.prompt = 'PS C:\\\\Users\\\\you\\\\projects\\\\ai-study-companion> '; T.showPrompt(); }""",
    "type_copy": """async (D) => { await T.type('copy .env.example .env'); T.enter(); T.showPrompt();
        callout('macOS or Linux:&nbsp; <code>cp .env.example .env</code>', 980, 760); }""",
    "editor_open": "async (D) => { hideCallout(); E.open(D.env); front('editor'); }",
    "editor_groq": """async (D) => { E.scrollTo(E.idx('# --- Chat model')); await sleep(800); E.focus('GROQ_API_KEY=');
        await sleep(500); await E.typeAfter('GROQ_API_KEY=', 'gsk_paste-your-key-here'); }""",
    "editor_gemini": """async (D) => { E.focus(['GEMINI_API_KEY=', 'LLM_PROVIDER=']);
        callout('Using Gemini instead? Paste it on <code>GEMINI_API_KEY</code> and set <code>LLM_PROVIDER=gemini</code>', 260, 905); }""",
    "editor_save": """async (D) => { E.save(); E.focus([]);
        callout('<code>.env</code> is in <code>.gitignore</code>, so git never commits your key', 260, 905, 'green'); }""",
    "editor_close": "async (D) => { hideCallout(); E.close(); front('main'); }",
    "type_dev": """async (D) => { await T.type('powershell -ExecutionPolicy Bypass -File scripts/dev.ps1'); T.enter();
        callout('macOS or Linux:&nbsp; <code>./scripts/dev.sh</code>', 1100, 800); }""",
    "out_install": """async (D) => { await sleep(600); hideCallout(); await T.print(D.pip, 85);
        await T.print([['', '{y}' + D.dev_secret + '{/}']], 0); await sleep(250); await T.print(D.npm, 250);
        await T.print([['', '{g}' + D.dev_ready + '{/}']], 0); T.showPrompt(); }""",
    "panes": """async (D) => { backdrop('main', true); showWin('backend'); front('backend'); await sleep(350); await B.print(D.uvicorn, 260);
        showWin('frontend'); front('frontend'); await sleep(300); await F.print(D.vite, 160); }""",
    "out_ready": """async (D) => { front('backend'); await B.print(D.model_download.slice(0, 1), 0); await sleep(2400);
        B.el.lastChild.remove(); await B.print(D.model_download.slice(1), 0); B.highlight('Fetching 5 files: 100%');
        await sleep(2600); B.highlight('Application startup complete'); F.highlight('http://localhost:5173/');
        callout('Open <code>http://localhost:5173</code> in your browser', 1110, 740, 'green'); }""",
    "docker_secret": """async (D) => { hideCallout(); hideWin('backend'); hideWin('frontend'); backdrop('main', false); front('editor');
        if (document.querySelector('#edScroller .ln')) E.show(); else E.open(D.env);
        E.scrollTo(E.idx('# Required in production')); await sleep(700);
        E.focus(['# Required in production', '#   python -c', 'SECRET_KEY=']);
        callout('Docker runs in production mode: <code>SECRET_KEY</code> needs a long random value', 260, 905, 'amber'); }""",
    "type_docker": """async (D) => { hideCallout(); E.close(); front('main'); await sleep(400);
        await T.type('docker compose up --build');
        callout('One container with the API and the web app: <code>http://localhost:8000</code>', 980, 760); }""",
}


class Terminal(Performer):
    def __init__(self, page: Any) -> None:
        super().__init__()
        self.page = page
        data = json.loads((HERE / "terminal_output.json").read_text(encoding="utf-8"))
        data["env"] = (ROOT / ".env.example").read_text(encoding="utf-8").rstrip("\n")
        self.data = data

    async def setup(self, scene: dict, retry: bool) -> None:
        if scene["id"] == "s08-clone" or retry:
            await self.page.reload()
            await self.page.evaluate("() => window.ready")
            await asyncio.sleep(0.5)

    async def run(self, scene: dict, beat: dict) -> None:
        for action in beat.get("do") or []:
            await self.page.evaluate(TERMINAL_ACTIONS[action], self.data)


# ----------------------------------------------------------------------------- app

class App(Performer):
    """Drives the real app inside browser.html with a visible cursor."""

    def __init__(self, page: Any, run: dict) -> None:
        super().__init__()
        self.page = page
        self.run_state = run

    @property
    def f(self) -> Any:
        frame = self.page.frame(name="app")
        if frame is None:
            raise SceneFailed("app frame missing")
        return frame

    def L(self, target: Any) -> Any:
        return self.f.locator(target).first if isinstance(target, str) else target

    # -- primitives
    async def box(self, target: Any) -> dict:
        loc = self.L(target)
        await loc.wait_for(state="visible", timeout=45_000)
        await loc.scroll_into_view_if_needed()
        b = await loc.bounding_box()
        if b and (b["y"] < 178 or b["y"] + b["height"] > H - 24):
            # hidden under the app's sticky top bar, or cut off at the bottom: bring it to the middle
            await loc.evaluate("el => el.scrollIntoView({block: 'center', behavior: 'smooth'})")
            await asyncio.sleep(0.75)
            b = await loc.bounding_box()
        if not b:
            raise SceneFailed(f"no bounding box for {target}")
        return b

    async def glide(self, target: Any, ms: int = 650) -> tuple[float, float]:
        b = await self.box(target)
        x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
        await self.page.evaluate("([x, y, ms]) => cursorTo(x, y, ms)", [x, y, ms])
        await self.page.mouse.move(x, y)
        return x, y

    async def click(self, target: Any, ms: int = 650, pause: float = 0.25) -> None:
        x, y = await self.glide(target, ms)
        b = await self.L(target).bounding_box()  # the page may still be settling after a scroll
        if b:
            nx, ny = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
            if abs(nx - x) > 3 or abs(ny - y) > 3:
                await self.page.evaluate("([x, y, ms]) => cursorTo(x, y, ms)", [nx, ny, 220])
                await self.page.mouse.move(nx, ny)
                x, y = nx, ny
        await asyncio.sleep(0.06)
        await self.page.evaluate("([x, y]) => ripple(x, y)", [x, y])
        await self.page.mouse.click(x, y)
        await asyncio.sleep(pause)

    async def type(self, target: Any, text: str, delay: int = 40) -> None:
        await self.click(target)
        loc = self.L(target)
        await loc.fill("")
        await loc.press_sequentially(text, delay=delay)

    async def select(self, target: Any, **option: Any) -> None:
        x, y = await self.glide(target)
        await self.page.evaluate("([x, y]) => ripple(x, y)", [x, y])
        await self.L(target).select_option(**option)
        await asyncio.sleep(0.35)

    async def check(self, target: Any) -> None:
        """Tick a checkbox and wait until it shows as ticked (some are saved to the server first)."""
        loc = self.L(target)
        if await loc.is_checked():
            await self.glide(target)
            return
        await self.click(target)
        for _ in range(40):
            if await loc.is_checked():
                return
            await asyncio.sleep(0.15)
        raise SceneFailed(f"checkbox did not tick: {target}")

    async def spot(self, target: Any = None, pad: int = 10, hold: float = 0.0) -> None:
        if target is None:
            await self.page.evaluate("() => spot(null)")
        else:
            b = await self.box(target)
            await self.page.evaluate("([r, p]) => spot(r, p)", [b, pad])
        if hold:
            await asyncio.sleep(hold)

    async def park(self, x: float = 1840, y: float = 640, ms: int = 500) -> None:
        """Move the cursor out of the way (empty right margin) so it never covers what is being read."""
        await self.page.evaluate("([x, y, ms]) => cursorTo(x, y, ms)", [x, y, ms])
        await self.page.mouse.move(x, y)

    async def at(self, fraction: float) -> None:
        """Wait until this fraction of the current beat's narration has been spoken."""
        rest = self.beat_start + self.beat_dur * fraction - time.time()
        if rest > 0:
            await asyncio.sleep(rest)

    async def hold(self, fraction: float, minimum: float = 2.0) -> None:
        """Keep what is on screen until this fraction of the narration, and for at least `minimum` seconds
        (a slow model can push the action past the narration; a highlight must never just flash)."""
        rest = self.beat_start + self.beat_dur * fraction - time.time()
        await asyncio.sleep(max(minimum, rest))

    async def callout_near(self, target: Any, html: str, dx: float = 0, dy: float = 14) -> None:
        b = await self.box(target)
        await self.page.evaluate("([h, x, y]) => callout(h, x, y)", [html, max(20, b["x"] + dx), b["y"] + b["height"] + dy])

    async def hover(self, target: Any, hold: float = 0.4) -> None:
        await self.glide(target)
        await asyncio.sleep(hold)

    async def key(self, key: str, label: str | None = None, hint: str | None = None) -> None:
        await self.page.evaluate("([l, h]) => keycap(l, h)", [label or key, hint])
        await self.page.keyboard.press(key)

    async def scroll_to(self, target: Any, block: str = "center", wait: float = 0.9) -> None:
        await self.page.evaluate("() => spot(null)")  # the highlight would not follow the scrolling page
        await self.L(target).evaluate("(el, b) => el.scrollIntoView({behavior: 'smooth', block: b})", block)
        await asyncio.sleep(wait)

    async def wheel(self, dy: float, steps: int = 8, pause: float = 0.05) -> None:
        await self.page.evaluate("() => spot(null)")
        for _ in range(steps):
            await self.page.mouse.wheel(0, dy / steps)
            await asyncio.sleep(pause)
        await asyncio.sleep(0.45)  # let the smooth scroll finish before anything measures the page

    async def wait(self, target: Any, timeout: float = 60) -> None:
        await self.L(target).wait_for(state="visible", timeout=timeout * 1000)

    async def tab(self, label: str) -> None:
        selected = f"button[role='tab'][aria-selected='true']:text-is('{label}')"
        for _ in range(2):
            await self.click(f"button[role='tab']:text-is('{label}')")
            try:
                await self.f.locator(selected).wait_for(timeout=3000)
                return
            except Exception:  # noqa: BLE001 - one retry, then fail the scene
                continue
        raise SceneFailed(f"tab {label} did not open")

    async def nav(self, href: str) -> None:
        await self.click(f"nav a[href='{href}']")

    async def settle(self, seconds: float = 0.6) -> None:
        await asyncio.sleep(seconds)

    async def check_errors(self) -> None:
        toast = self.f.locator("[data-sonner-toast][data-type='error']")
        if await toast.count():
            raise SceneFailed(f"error toast: {(await toast.first.inner_text())[:200]}")

    async def until(self, success: Any, timeout: float = 240, speed: float = 6.0) -> None:
        """Wait for a slow step (a model call, indexing) and compress the waiting in the edit."""
        start = time.time()
        loc = self.L(success)
        while True:
            if await loc.count() and await loc.is_visible():
                break
            await self.check_errors()
            if time.time() - start > timeout:
                raise SceneFailed(f"timed out waiting for {success}")
            await asyncio.sleep(0.25)
        self.compress(start, time.time(), speed)  # before cueing: the cue moves narration_end
        self.cue_now()

    def url(self) -> str:
        return self.f.url

    async def goto(self, path: str) -> None:
        await self.f.goto(f"{APP}{path}", wait_until="load")
        await asyncio.sleep(0.8)

    # -- scene setup (not recorded): only needed when a scene is recorded on its own or retried
    async def setup(self, scene: dict, retry: bool) -> None:
        await self.page.evaluate("() => { spot(null); callout(null); setAddress(null) }")
        sid = scene["id"]
        if sid == "s11-register":
            await self.goto("/register")
            await self.f.evaluate("() => localStorage.removeItem('asc_token')")
            self.run_state["email"] = f"asha.verma{int(time.time()) % 100000}@example.com"
            await self.goto("/register")
            await self.wait("text=Create your study space")
            return
        if not await self.f.evaluate("() => Boolean(localStorage.getItem('asc_token'))"):
            await self.login()
        start = SCENE_START.get(sid)
        if start and (retry or self.run_state.get("only")):
            await self.goto(start)
        if sid == "s21-apidocs":
            warm = await self.page.context.new_page()
            await warm.goto(f"{API}/api/docs")
            await warm.wait_for_selector(".opblock-tag", timeout=60_000)
            await warm.close()
        await self.page.evaluate("() => callout(null)")
        await asyncio.sleep(0.5)

    async def login(self) -> None:
        email, password = self.run_state.get("email"), self.run_state["password"]
        if not email:
            raise SceneFailed("no demo account yet: record s11-register first")
        token = await self.f.evaluate(
            """async ([e, p]) => { const r = await fetch('/api/v1/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email: e, password: p})});
               if (!r.ok) return null; const j = await r.json(); return j.access_token || j.token || null }""",
            [email, password],
        )
        if not token:
            raise SceneFailed("login failed")
        await self.f.evaluate("(t) => localStorage.setItem('asc_token', t)", token)
        await self.goto("/")

    async def run(self, scene: dict, beat: dict) -> None:
        for action in beat.get("do") or []:
            await APP_ACTIONS[action](self)
        await self.check_errors()


SCENE_START = {
    "s12-settings": "/",
    "s13-upload": "/settings",
    "s14-search": "/notes",
    "s15-tutor": "/notes",
    "s16-quiz": "/tutor",
    "s17-flashcards": "/quizzes",
    "s18-tools": "/revision?tab=flashcards",
    "s19-syllabus": "/revision?tab=plan",
    "s20-dashboard": "/syllabus",
    "s21-apidocs": "/",
}


def card(title: str) -> str:
    return f"section.card:has(h3:text-is('{title}'))"


def provider_card(app: App, name: str) -> Any:
    return app.f.locator("button").filter(has=app.f.locator("span.font-semibold", has_text=re.compile(rf"^{re.escape(name)}$"))).first


# -- s11 register
async def register_fill(a: App) -> None:
    await a.type("input[autocomplete='name']", "Asha Verma", delay=75)
    await a.type("input[type='email']", a.run_state["email"], delay=40)
    await a.type("input[type='password']", a.run_state["password"], delay=45)


async def register_submit(a: App) -> None:
    await a.click("button:has-text('Create account')")
    await a.wait("text=Recommended next", 30)
    await a.settle(1.0)
    await a.hover("aside nav")


# -- s12 settings
async def settings_open(a: App) -> None:
    await a.nav("/settings")
    await a.wait("text=Choose a provider")


async def settings_tour(a: App) -> None:
    await a.spot(card("Active model"), hold=2.2)
    await a.scroll_to(card("Choose a provider"), block="start")
    await a.spot(card("Choose a provider"), hold=1.6)
    await a.spot(a.f.locator("span", has_text=re.compile(r"^free tier$")).first, pad=6, hold=1.2)
    await a.spot()


async def settings_groq(a: App) -> None:
    await a.click(provider_card(a, "Groq"))
    await a.scroll_to("input[type='password']")
    await a.spot("label:has(input[type='password'])", hold=1.8)
    await a.hover("a:has-text('Where to get a key')", hold=1.0)
    await a.spot()


async def settings_gemini(a: App) -> None:
    await a.scroll_to(card("Choose a provider"), block="start")
    await a.click(provider_card(a, "Google Gemini"))
    await a.type("input[list='model-list']", a.run_state["model"], delay=40)  # scrolls only as far as needed
    await a.spot(provider_card(a, "Google Gemini"), pad=6, hold=1.0)
    await a.spot()


async def settings_load_test(a: App) -> None:
    await a.click("button[title='Load models']")
    await a.until("form button.chip", timeout=60, speed=4.0)
    await a.settle(0.8)
    await a.click("button:has-text('Test connection')")
    await a.until("text=/replied in/", timeout=90, speed=4.0)
    await a.spot("span:has-text('replied in')", pad=6, hold=1.0)
    await a.spot()


async def settings_save(a: App) -> None:
    await a.click("button:has-text('Save as my model')")
    await a.until("[data-sonner-toast]:has-text('Now using')", timeout=30)
    await a.scroll_to(card("Active model"), block="center")
    await a.spot(card("Active model"), hold=1.2)
    await a.spot()


# -- s13 upload
async def notes_open(a: App) -> None:
    await a.nav("/notes")
    await a.wait("text=Drag notes here")


async def notes_tag(a: App) -> None:
    await a.type("input[placeholder*='OS Unit 4']", "Database Design (Watt & Eng)", delay=40)
    await a.select(f"{card('Tag the upload')} label:has-text('Subject') select", label="BCS501 · Database Management System (Sem 5)")
    await a.hover(f"{card('Tag the upload')} label:has-text('Unit') select", hold=0.6)
    await a.park()


async def notes_upload(a: App) -> None:
    zone = "div:has(> input[data-testid='file-input'])"
    x, y = await a.glide(zone)
    await a.page.evaluate("([x, y]) => ripple(x, y)", [x, y])
    await a.f.locator("[data-testid='file-input']").set_input_files(str(BOOK))
    await a.until("tr:has-text('Database Design')", timeout=60, speed=4.0)
    await a.spot("tr:has-text('Database Design')", pad=6)


async def notes_wait_ready(a: App) -> None:
    await a.until("tr:has-text('Database Design'):has-text('Ready')", timeout=600, speed=8.0)
    await a.spot("tr:has-text('Database Design')", pad=6, hold=0.3)


# -- s14 search
async def search_type(a: App) -> None:
    await a.spot()
    target = "input[placeholder*='page replacement']"
    await a.scroll_to(card("Search your notes"), block="start")
    await a.type(target, "second normal form partial dependency", delay=45)
    await a.key("Enter", "Enter")
    await a.until(f"{card('Search your notes')} li mark", timeout=60, speed=4.0)
    await a.park()


async def search_spot(a: App) -> None:
    first = f"{card('Search your notes')} li >> nth=0"
    await a.spot(first, pad=6, hold=2.2)
    await a.spot(f"{card('Search your notes')} li >> nth=0 >> mark >> nth=0", pad=5, hold=1.6)
    await a.spot(f"{card('Search your notes')} li >> nth=0 >> span.ml-auto", pad=6, hold=1.6)
    await a.spot()


async def search_modes(a: App) -> None:
    for mode in ("keyword", "semantic", "hybrid"):
        await a.click(f"{card('Search your notes')} button:text-is('{mode}')", ms=450)
        await a.until(f"{card('Search your notes')} li", timeout=30, speed=4.0)
        await a.settle(0.45)
    await a.park()


async def search_open_passage(a: App) -> None:
    await a.click(f"{card('Search your notes')} li >> nth=0 >> button.font-semibold")
    await a.wait("div[role='dialog'] [id^='chunk-page-'].border-brand-300", 30)  # the passage's page, highlighted
    await a.settle(1.0)
    await a.park()


QUESTION = "Explain the difference between a primary key and a foreign key with an example"


async def tutor_ask(a: App) -> None:
    await a.key("Escape", "Esc")
    await a.settle(0.3)
    await a.nav("/tutor")
    await a.wait("text=Ask anything from your notes")
    await a.type("textarea", QUESTION, delay=28)
    await a.key("Enter", "Enter")


async def tutor_wait_style(a: App) -> None:
    await a.until("button[title='Copy']", timeout=150, speed=3.0)
    await a.settle(0.4)
    style = "select[title='Answer style']"
    await a.spot(style, pad=6)
    await a.callout_near(style, "Exam answer · Explain simply · Detailed · Short · Step by step · Practice questions", dx=-430)
    await a.hold(0.95, 3.0)
    await a.page.evaluate("() => callout(null)")
    await a.spot()


async def tutor_spot_cite(a: App) -> None:
    chip = "button.cite-chip >> nth=0"
    await a.scroll_to(chip)
    await a.spot(chip, pad=6, hold=1.0)
    await a.hover(chip)


async def tutor_open_sources(a: App) -> None:
    await a.spot()
    await a.click("button.cite-chip >> nth=0")
    await a.wait("text=Sources used in this answer", 20)
    await a.park()
    await a.settle(0.5)
    excerpt = "div[role='dialog'] div.rounded-xl.bg-slate-50 p"
    await a.spot(excerpt, pad=8)
    await a.hold(0.5, 1.8)
    await a.spot("div[role='dialog'] div.rounded-xl.bg-slate-50 div.mb-2", pad=6)
    await a.hold(0.97, 1.8)
    await a.spot()


async def tutor_close_sources(a: App) -> None:
    await a.key("Escape", "Esc")
    await a.settle(0.4)
    chip = "button:has-text('from your notes') >> nth=-1"
    await a.scroll_to(chip)
    await a.park()
    await a.spot(chip, pad=6)
    await a.hold(0.95, 2.0)
    await a.spot()


async def tutor_actions(a: App) -> None:
    await a.scroll_to("button[title='Copy'] >> nth=-1")
    await a.spot("span.ml-auto:has(button[title='Copy']) >> nth=-1", pad=6, hold=1.0)
    await a.click("button[title='Bookmark'] >> nth=-1")
    await a.click("button[title='Helpful'] >> nth=-1")
    await a.spot()


async def tutor_followup(a: App) -> None:
    follow = "button.rounded-full.border-brand-200 >> nth=0"
    await a.scroll_to(follow)
    await a.click(follow)
    await a.park()
    await a.until("button[title='Copy'] >> nth=1", timeout=150, speed=4.0)
    await a.settle(0.5)


async def tutor_filter_turninto(a: App) -> None:
    await a.click("button:has-text('All notes')")
    await a.wait("text=Limit answers to specific notes", 10)
    await a.click("div[role='dialog'] button:has-text('Database Design')")
    await a.click("button:text-is('Done')")
    await a.click("button:has-text('Turn into')")
    await a.hover("button:has-text('Flashcards') >> nth=-1", hold=0.4)
    await a.hover("button:has-text('Summary') >> nth=-1", hold=0.4)
    await a.click("button:has-text('Quiz on this topic')")
    await a.wait("text=Generate a quiz", 15)  # the quiz form opens with the question and the notes filled in
    await a.spot("div[role='dialog'] div.relative", pad=4)
    await a.hold(0.98, 2.0)
    await a.spot()
    await a.key("Escape", "Esc")


async def quiz_new(a: App) -> None:
    await a.nav("/quizzes")
    await a.wait("text=Quizzes & Grading")
    await a.click("button:has-text('New quiz')")
    await a.wait("text=Generate a quiz", 10)


async def ensure_doc_chip(a: App, scope: str = "div[role='dialog']") -> None:
    chip = a.f.locator(f"{scope} button:has-text('Database Design')").first
    if "border-brand-300" in (await chip.get_attribute("class") or ""):
        await a.hover(chip, hold=0.3)  # already selected (carried over from the tutor's filter)
    else:
        await a.click(chip)


async def quiz_form(a: App) -> None:
    modal = "div[role='dialog']"
    await a.type(f"{modal} input[placeholder*='CPU scheduling']", "Normalization and functional dependencies", delay=16)
    await a.select(f"{modal} label:has-text('Subject') select", label="BCS501 · Database Management System (Sem 5)")
    await a.at(0.45)
    await ensure_doc_chip(a)
    await a.at(0.62)
    await a.select(f"{modal} label:has-text('Questions') select", value="5")
    await a.hover(f"{modal} label:has-text('Difficulty') select", hold=0.3)
    await a.at(0.85)
    await a.select(f"{modal} label:has-text('Timer') select", value="600")


async def quiz_generate(a: App) -> None:
    await a.spot("div[role='dialog'] label:has-text('Question types')", pad=6)
    await a.hold(0.82, 1.5)
    await a.spot()
    await a.click("button:has-text('Generate quiz')")
    await a.park()
    await a.until("text=/^Q1$/", timeout=180, speed=6.0)
    await a.settle(0.8)


def _quiz_questions(quiz_id: int) -> list[dict]:
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("select qtype, options, answer_key from questions where quiz_id = ? order by position", (quiz_id,)).fetchall()
    finally:
        con.close()
    out = []
    for qtype, options, key in rows:
        try:
            opts = json.loads(options) if options else []
        except (TypeError, ValueError):
            opts = []
        out.append({"qtype": qtype, "options": opts or [], "key": key or ""})
    return out


async def quiz_answer(a: App) -> None:
    """Answer like a real student: mostly right, one multiple-choice slip, a short written answer.
    The answer keys come from the local database so the outcome is not left to chance; grading stays real."""
    started = time.time()
    m = re.search(r"/quizzes/(\d+)", a.url())
    if not m:
        raise SceneFailed(f"not on a quiz page: {a.url()}")
    questions = _quiz_questions(int(m.group(1)))
    slipped = False
    for i, q in enumerate(questions):
        if i > 0:
            await a.click(f"button[aria-label='Question {i + 1}']", ms=450)
        options = a.f.locator("main button.flex.w-full")
        if q["qtype"] == "short_answer":
            words = re.sub(r"\s+", " ", q["key"]).split(" ")
            answer = " ".join(words[:28]).rstrip(",;:") + "."
            await a.type("main textarea", answer, delay=14)
        elif q["qtype"] == "true_false":
            await a.click(a.f.locator("main button.flex.w-full", has_text=re.compile(rf"^\s*\w?\s*{re.escape(q['key'].strip())}\s*$", re.I)).first, ms=450)
        else:
            letters = "ABCDEFGH"
            key = (q["key"].strip()[:1] or "A").upper()
            idx = letters.index(key) if key in letters else 0
            if not slipped and await options.count() > 1:
                idx, slipped = (idx + 1) % await options.count(), True
            await a.click(options.nth(idx), ms=450)
        await a.settle(0.35)
    a.page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await a.click("button:has-text('Submit quiz')")
    a.compress(started, time.time(), 2.0)


async def quiz_result(a: App) -> None:
    await a.until("button:has-text('Retake')", timeout=180, speed=6.0)
    await a.park()
    await a.settle(0.8)
    await a.spot("main section.card >> nth=0", pad=6, hold=2.0)
    short = "main section.card:has-text('Model answer')"
    if await a.f.locator(short).count():
        await a.scroll_to(short)
        await a.spot(short, pad=6, hold=1.5)
    await a.spot()


async def quiz_breakdown(a: App) -> None:
    if await a.f.locator(card("Topic breakdown")).count():
        await a.scroll_to(card("Topic breakdown"))
        await a.spot(card("Topic breakdown"), pad=6, hold=2.0)
    await a.spot()
    await a.scroll_to("main section.card:has-text('Correct answer') >> nth=0")
    await a.spot("main section.card:has-text('Correct answer') >> nth=0", pad=6, hold=1.8)
    await a.spot()


async def quiz_weak(a: App) -> None:
    await a.spot()
    await a.f.evaluate("() => window.scrollTo({top: 0, behavior: 'smooth'})")
    await a.settle(0.8)
    weak = "main section.card >> nth=0 >> div.flex.flex-wrap.gap-2.text-xs"
    if await a.f.locator(weak).count():
        await a.spot(weak, pad=6)
    await a.hold(0.25, 1.6)
    await a.spot()
    for label in ("Retake", "Ask tutor about", "Flashcards for weak topics"):
        target = f"main button:has-text('{label}')"
        if await a.f.locator(target).count():
            await a.hover(target, hold=0.7)
    await a.park()


async def cards_generate(a: App) -> None:
    await a.nav("/revision")
    await a.wait("text=New deck from notes")
    await a.click("button:has-text('New deck from notes')")
    await a.wait("text=Generate flashcards", 10)
    await a.type("div[role='dialog'] input[placeholder*='Deadlock']", "Entity relationship model", delay=40)
    await a.click("div[role='dialog'] button:has-text('Database Design')")
    await a.click("button:has-text('Create deck')")
    await a.until("button:has-text('Review all due'):not([disabled])", timeout=180, speed=6.0)
    await a.settle(0.6)


async def cards_review(a: App) -> None:
    await a.click("button:has-text('Review all due')")
    await a.wait("text=Click or press space to reveal", 20)
    await a.park(1540, 700)  # beside the card, not on it
    await a.settle(0.6)
    await a.key("Space", "Space", "flip")
    await a.settle(1.8)
    await a.click("button:has-text('Good')")
    await a.park(1540, 700)
    await a.settle(0.7)
    await a.key("Space", "Space", "flip")
    await a.settle(1.5)
    await a.key("4", "4", "Easy")
    await a.settle(0.9)


async def cards_finish(a: App) -> None:
    await a.key("Space", "Space", "flip")
    await a.settle(1.4)
    await a.key("1", "1", "Again: back in 10 minutes")
    await a.settle(0.9)
    await a.key("Space", "Space", "flip")
    await a.settle(1.2)
    await a.key("3", "3", "Good")
    await a.settle(0.9)
    await a.click("button:has-text('Exit session')")
    await a.wait("text=Due now", 10)
    await a.spot("div.grid:has-text('Due now')", pad=8, hold=1.2)
    await a.spot()


# -- s18 tools
async def tools_summary_form(a: App) -> None:
    await a.tab("Summaries")
    await a.click("button:has-text('New summary')")
    await a.wait("text=Generate a revision summary", 10)
    await a.type("div[role='dialog'] input[placeholder*='Deadlock']", "Normalization", delay=45)
    await a.click("div[role='dialog'] button:has-text('Database Design')")
    await a.click("button:has-text('Summarise')")


async def tools_summary_result(a: App) -> None:
    await a.until("text=/60-second revision/i", timeout=180, speed=6.0)
    await a.settle(0.6)
    await a.wheel(700, steps=12, pause=0.14)
    await a.settle(1.2)
    await a.wheel(900, steps=12, pause=0.14)
    await a.park(560, 760)


async def tools_keywords_form(a: App) -> None:
    await a.tab("Keywords")
    await a.click("button:has-text('Extract keywords')")
    await a.wait("text=Extract exam keywords", 10)
    await a.type("div[role='dialog'] input[placeholder*='Deadlock']", "Relational model and keys", delay=40)
    await a.click("div[role='dialog'] button:has-text('Database Design')")
    await a.click("div[role='dialog'] button:has-text('Extract')")


async def tools_keywords_result(a: App) -> None:
    await a.until("main span:text-is('high')", timeout=180, speed=6.0)
    await a.settle(0.6)
    await a.spot("main span:text-is('high') >> nth=0", pad=6, hold=1.4)
    await a.spot()
    await a.wheel(500, steps=10, pause=0.12)


async def tools_map_form(a: App) -> None:
    await a.tab("Concept maps")
    await a.click("button:has-text('New concept map')")
    await a.wait("text=Generate a concept map", 10)
    await a.type("div[role='dialog'] input[placeholder*='Deadlock']", "Entity relationship modelling", delay=40)
    await a.click("div[role='dialog'] button:has-text('Database Design')")
    await a.click("button:has-text('Build map')")


async def tools_map_result(a: App) -> None:
    await a.until(".react-flow__node", timeout=180, speed=6.0)
    await a.settle(1.0)
    node = ".react-flow__node >> nth=1"
    x, y = await a.glide(node)
    await a.page.mouse.down()
    for k in range(1, 15):
        await a.page.mouse.move(x + 7 * k, y + 4 * k)
        await a.page.evaluate("([x, y]) => cursorTo(x, y, 30)", [x + 7 * k, y + 4 * k])
        await asyncio.sleep(0.03)
    await a.page.mouse.up()
    await a.settle(0.3)
    await a.glide(".react-flow__pane")
    await a.wheel(-160, steps=5, pause=0.08)
    await a.settle(0.3)
    await a.wheel(220, steps=5, pause=0.08)
    await a.spot("button:has-text('Copy as Mermaid')", pad=6)
    await a.hover("button:has-text('Copy as Mermaid')", hold=0.2)
    await a.hold(0.98, 1.6)
    await a.spot()


async def tools_plan_form(a: App) -> None:
    await a.tab("Study plan")
    await a.click("button:has-text('New study plan')")
    await a.wait("text=Plan my revision", 10)
    exam = time.strftime("%Y-%m-%d", time.localtime(time.time() + 21 * 86400))
    date = "div[role='dialog'] input[type='date']"
    x, y = await a.glide(date)  # no real click: it would open the native date picker
    await a.page.evaluate("([x, y]) => ripple(x, y)", [x, y])
    await a.f.locator(date).fill(exam)
    # the subject rows are labels nested inside the field's own label, so match the row by its code
    await a.check("div[role='dialog'] label:has(> span:text-is('BCS501')) > input[type='checkbox']")
    await a.check("div[role='dialog'] label:has(> span:text-is('BCS401')) > input[type='checkbox']")
    await a.type("div[role='dialog'] input[placeholder*='numericals']", "previous-year questions", delay=40)
    await a.click("button:has-text('Create plan')")


async def tools_plan_result(a: App) -> None:
    await a.until("text=/Exam on/", timeout=240, speed=6.0)
    await a.settle(0.8)
    await a.wheel(700, steps=12, pause=0.14)


# -- s19 syllabus
async def syllabus_open(a: App) -> None:
    await a.nav("/syllabus")
    await a.wait("text=Semester 3")
    await a.settle(0.8)
    await a.wheel(500, steps=8, pause=0.1)


async def syllabus_subject(a: App) -> None:
    await a.click("a:has-text('Database Management System')")
    await a.wait("text=Unit 1", 20)
    await a.settle(0.6)
    await a.check("main input[type='checkbox'] >> nth=0")
    await a.check("main input[type='checkbox'] >> nth=1")
    await a.settle(0.5)


async def syllabus_lectures(a: App) -> None:
    unit = "main section.card >> nth=0"
    await a.spot(f"{unit} >> div.ml-auto", pad=6)
    await a.hold(0.72, 1.5)  # click "Lectures" as the narration reaches "find lectures"
    await a.spot()
    await a.click(f"{unit} >> button:has-text('Lectures')")


async def lectures_results(a: App) -> None:
    await a.until("text=/Recommended channels|live search/", timeout=90, speed=6.0)
    start = time.time()
    while time.time() - start < 20:  # wait for the video thumbnails, so no blank cards are shown
        loaded = await a.f.evaluate("() => [...document.querySelectorAll('main img')].every(i => i.complete && i.naturalWidth > 0)")
        if loaded:
            break
        await asyncio.sleep(0.25)
    a.compress(start, time.time(), 4.0)
    await a.park()
    await a.settle(0.8)
    await a.wheel(600, steps=10, pause=0.1)
    if await a.f.locator(card("Recommended channels")).count():
        await a.scroll_to(card("Recommended channels"))
        await a.spot(card("Recommended channels"), pad=6, hold=1.2)
        await a.spot()


async def history_search(a: App) -> None:
    await a.nav("/history")
    await a.wait("text=Every question and answer is indexed")
    await a.type("input[placeholder*='Search past conversations']", "foreign key", delay=55)
    await a.key("Enter", "Enter")
    await a.settle(1.2)
    await a.scroll_to(card("Bookmarked answers"))
    await a.spot(card("Bookmarked answers"), pad=6, hold=1.4)
    await a.spot()


async def dashboard_open(a: App) -> None:
    await a.nav("/")
    await a.wait("text=Accuracy by topic")
    await a.settle(0.8)
    await a.spot("main div.grid:has-text('Notes indexed') >> nth=0", pad=8, hold=2.0)
    await a.spot()


async def dashboard_tour(a: App) -> None:
    await a.spot(card("Accuracy by topic"), pad=6, hold=2.4)
    await a.spot(card("Recommended next"), pad=6, hold=2.4)
    await a.spot()
    await a.scroll_to(card("Last 14 days"))
    await a.settle(1.0)
    await a.scroll_to(card("Syllabus progress"))


# -- s21 API docs
async def docs_open(a: App) -> None:
    await a.page.evaluate("(t) => typeAddress(t)", "localhost:8000/api/docs")
    await a.f.goto(f"{API}/api/docs")
    await a.wait(".opblock-tag", 30)
    await a.settle(0.8)


async def docs_tour(a: App) -> None:
    await a.glide(".opblock-tag >> nth=0")
    for _ in range(4):
        await a.wheel(500, steps=10, pause=0.1)
        await a.settle(0.6)
    target = ".opblock-summary:has(.opblock-summary-path[data-path='/api/v1/search'])"
    await a.scroll_to(target)
    await a.click(target)
    await a.settle(1.0)
    await a.wheel(260, steps=6, pause=0.08)


APP_ACTIONS: dict[str, Callable[[App], Awaitable[None]]] = {
    fn.__name__: fn
    for fn in (
        register_fill, register_submit,
        settings_open, settings_tour, settings_groq, settings_gemini, settings_load_test, settings_save,
        notes_open, notes_tag, notes_upload, notes_wait_ready,
        search_type, search_spot, search_modes, search_open_passage,
        tutor_ask, tutor_wait_style, tutor_spot_cite, tutor_open_sources, tutor_close_sources, tutor_actions, tutor_followup, tutor_filter_turninto,
        quiz_new, quiz_form, quiz_generate, quiz_answer, quiz_result, quiz_breakdown, quiz_weak,
        cards_generate, cards_review, cards_finish,
        tools_summary_form, tools_summary_result, tools_keywords_form, tools_keywords_result,
        tools_map_form, tools_map_result, tools_plan_form, tools_plan_result,
        syllabus_open, syllabus_subject, syllabus_lectures, lectures_results,
        history_search, dashboard_open, dashboard_tour,
        docs_open, docs_tour,
    )
}


# ----------------------------------------------------------------------------- record stage

async def _record(args: argparse.Namespace) -> None:
    from playwright.async_api import async_playwright

    script = load_script()
    audio = json.loads((args.build / "audio.json").read_text(encoding="utf-8"))
    state_file = args.build / "run_state.json"
    run_state = json.loads(state_file.read_text()) if state_file.exists() else {}
    run_state.update({"password": "study-companion-demo", "model": args.model, "only": bool(args.only)})
    only = set(args.only.split(",")) if args.only else None
    missing = [k for s in script["scenes"] for k in (f"{s['id']}#{i}" for i in range(len(s["beats"]))) if k not in audio]
    if missing:
        raise SystemExit(f"run the tts stage first; missing audio for {missing[:3]}")
    if not BOOK.exists():
        raise SystemExit(f"{BOOK} not found: run scripts/fetch_open_notes.py first")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)

        async def serve(route: Any) -> None:
            name = route.request.url.split("/__tutorial/", 1)[1].split("?")[0]
            path = HERE / name
            ctype = "text/html" if name.endswith(".html") else "image/png" if name.endswith(".png") else "application/octet-stream"
            await route.fulfill(path=str(path), content_type=ctype)

        await ctx.route(f"{SHELL}/**", serve)
        pages: dict[str, tuple[Any, Any, Performer]] = {}

        async def get(kind: str) -> tuple[Any, Any, Performer]:
            if kind in pages:
                return pages[kind]
            if kind in ("app", "apidocs") and ("app" in pages or "apidocs" in pages):
                pages[kind] = pages.get("app") or pages["apidocs"]
                return pages[kind]
            page = await ctx.new_page()
            if kind == "slide":
                await page.goto(f"{SHELL}/slides.html?slide=title&step=0")
                await page.evaluate("() => document.fonts.ready")
                performer: Performer = Slides(page)
            elif kind == "terminal":
                await page.goto(f"{SHELL}/terminal.html")
                await page.evaluate("() => window.ready")
                performer = Terminal(page)
            else:
                await page.goto(f"{SHELL}/browser.html")
                performer = App(page, run_state)
                page.set_default_timeout(45_000)
            await page.evaluate(TICK_JS)
            cdp = await ctx.new_cdp_session(page)
            pages[kind] = (page, cdp, performer)
            if kind in ("app", "apidocs"):
                pages["app"] = pages["apidocs"] = pages[kind]
            return pages[kind]

        for scene in script["scenes"]:
            if only and scene["id"] not in only:
                continue
            page, cdp, performer = await get(scene["kind"])
            await page.bring_to_front()
            for attempt in range(1, args.attempts + 1):
                try:
                    await record_scene(scene, page, cdp, performer, audio, args.build, retry=attempt > 1)
                    break
                except Exception as exc:  # noqa: BLE001 - any failure means the footage is unusable
                    print(f"[record] {scene['id']} attempt {attempt} failed: {exc}", flush=True)
                    shot = args.build / "failures" / f"{scene['id']}-{attempt}.png"
                    shot.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        await page.screenshot(path=str(shot))
                    except Exception:  # noqa: BLE001
                        pass
                    if attempt == args.attempts:
                        raise
                    await asyncio.sleep(args.retry_wait)
            state_file.write_text(json.dumps({k: v for k, v in run_state.items() if k in ("email",)}), encoding="utf-8")
        await browser.close()


def stage_record(args: argparse.Namespace) -> None:
    asyncio.run(_record(args))


# ----------------------------------------------------------------------------- assemble

class SceneClip:
    """Maps a scene's recorded wall-clock timeline to output time, compressing marked waits."""

    def __init__(self, tl: dict) -> None:
        self.tl = tl
        self.times = [t for t, _ in tl["frames"]]
        self.names = [n for _, n in tl["frames"]]
        warps = sorted(([a, b, s] for a, b, s in tl["warps"] if b > a), key=lambda w: w[0])
        merged: list[list[float]] = []
        for w in warps:
            if merged and w[0] <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], w[1])
                merged[-1][2] = max(merged[-1][2], w[2])
            else:
                merged.append(list(w))
        self.warps = merged
        self.duration = self.out(tl["end"])

    def out(self, t: float) -> float:
        """Source time -> output time."""
        shift = 0.0
        for a, b, s in self.warps:
            if t <= a:
                break
            span = min(t, b) - a
            shift += span - span / s
        return t - shift

    def src(self, u: float) -> float:
        """Output time -> source time."""
        t = u
        for a, b, s in self.warps:
            a_out = self.out(a)
            if u <= a_out:
                return u + (a - a_out)
            b_out = a_out + (b - a) / s
            if u <= b_out:
                return a + (u - a_out) * s
            t = b + (u - b_out)
        return t

    def warp_speed(self, u: float) -> float:
        t = self.src(u)
        for a, b, s in self.warps:
            if a <= t <= b:
                return s
        return 1.0

    def frame_at(self, u: float) -> str:
        t = self.src(u)
        i = bisect.bisect_right(self.times, t) - 1
        return self.names[max(0, i)]


def _font(size: int, bold: bool = True) -> Any:
    from PIL import ImageFont

    candidates = ["C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default(size=size)


def _chapter_badge(img: Any, number: int, title: str, alpha: float) -> Any:
    from PIL import Image, ImageDraw

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f1, f2 = _font(26), _font(38)
    label = f"CHAPTER {number}"
    w1 = d.textlength(label, font=f1)
    w2 = d.textlength(title, font=f2)
    box_w = int(max(w1, w2) + 80)
    x, y = 64, H - 210
    a = int(235 * alpha)
    d.rounded_rectangle([x, y, x + box_w, y + 132], radius=22, fill=(17, 24, 39, a))
    d.rounded_rectangle([x, y, x + 8, y + 132], radius=4, fill=(99, 102, 241, a))
    d.text((x + 40, y + 24), label, font=f1, fill=(165, 172, 248, int(255 * alpha)))
    d.text((x + 40, y + 60), title, font=f2, fill=(255, 255, 255, int(255 * alpha)))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _speed_badge(img: Any, speed: float) -> Any:
    from PIL import Image, ImageDraw

    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = W - 470, 17  # the empty right-hand part of the browser's tab strip
    d.rounded_rectangle([x, y, x + 168, y + 42], radius=21, fill=(79, 70, 229, 235))
    for k in (0, 1):
        ox = x + 20 + k * 16
        d.polygon([(ox, y + 12), (ox, y + 30), (ox + 14, y + 21)], fill=(255, 255, 255, 245))
    d.text((x + 64, y + 7), f"{speed:g}x", font=_font(24), fill=(255, 255, 255, 245))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _encode_segment(job: dict) -> str:
    """Encode a run of scenes to one H.264 segment: frames mapped to 30 fps, cross-fades and badges drawn."""
    from PIL import Image

    build, out = Path(job["build"]), Path(job["out"])
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", job["preset"], "-crf", str(job["crf"]), "-pix_fmt", "yuv420p", "-threads", "4", str(out)],
        stdin=subprocess.PIPE,
    )
    assert enc.stdin

    def load(path: Path) -> Any:
        img = Image.open(path).convert("RGB")
        return img if img.size == (W, H) else img.resize((W, H), Image.LANCZOS)

    first = job["scenes"][0]
    previous_last = load(Path(first["prev_last"])) if first["prev_last"] else None
    for spec in job["scenes"]:
        clip = SceneClip(json.loads((build / "timelines" / f"{spec['id']}.json").read_text(encoding="utf-8")))
        folder = build / "frames" / spec["id"]
        cache_name, cache_img, cache_bytes = None, None, b""
        for k in range(spec["n_frames"]):
            u = k / FPS
            name = clip.frame_at(u)
            if name != cache_name:
                cache_name, cache_img = name, load(folder / name)
                cache_bytes = cache_img.tobytes()
            frame = None
            if previous_last is not None and u < XFADE:
                frame = Image.blend(previous_last, cache_img, u / XFADE)
            if spec["badge"] and 0.3 < u < 4.2:
                alpha = min(1.0, (u - 0.3) / 0.4, (4.2 - u) / 0.5)
                if alpha > 0:
                    frame = _chapter_badge(frame or cache_img, spec["badge"], spec["chapter"], alpha)
            speed = clip.warp_speed(u)
            if speed >= 2.5:
                frame = _speed_badge(frame or cache_img, speed)
            enc.stdin.write(frame.tobytes() if frame is not None else cache_bytes)
        previous_last = cache_img
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out.name}")
    return str(out)


def stage_assemble(args: argparse.Namespace) -> None:
    import soundfile as sf

    script = load_script()
    audio = json.loads((args.build / "audio.json").read_text(encoding="utf-8"))
    scenes = [s for s in script["scenes"] if (args.build / "timelines" / f"{s['id']}.json").exists()]
    if args.only:
        wanted = set(args.only.split(","))
        scenes = [s for s in scenes if s["id"] in wanted]
    if not scenes:
        raise SystemExit("nothing recorded yet")
    clips = {s["id"]: SceneClip(json.loads((args.build / "timelines" / f"{s['id']}.json").read_text(encoding="utf-8"))) for s in scenes}

    # ---- timeline: scene offsets, narration placement, subtitles, chapters
    n_frames = {sid: int(round(c.duration * FPS)) for sid, c in clips.items()}
    offsets, cursor = {}, 0.0
    for s in scenes:
        offsets[s["id"]] = cursor
        cursor += n_frames[s["id"]] / FPS  # whole frames, so narration and video never drift apart
    total = cursor
    track = np.zeros(int((total + 1) * SR), dtype=np.float32)
    cues: list[tuple[float, float, str]] = []
    chapters: list[tuple[float, str]] = []
    chapter_no = {}
    for s in scenes:
        if s.get("_chapter_start") or not chapters:
            chapters.append((offsets[s["id"]], s["_chapter"]))
            chapter_no[s["id"]] = len(chapters)
        clip = clips[s["id"]]
        for beat in clip.tl["beats"]:
            entry = audio[f"{s['id']}#{beat['index']}"]
            samples, sr = sf.read(str(args.build / "audio" / entry["file"]), dtype="float32")
            assert sr == SR, sr
            start = offsets[s["id"]] + clip.out(beat["t"])
            i = int(start * SR)
            track[i: i + len(samples)] += samples[: max(0, len(track) - i)]
            b = s["beats"][beat["index"]]
            cues.extend(_cues(b.get("sub") or written(spoken(b)), start, entry["duration"]))
    out_dir = args.build / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "narration.wav"
    sf.write(str(wav), np.clip(track, -1, 1), SR, subtype="PCM_16")
    srt = out_dir / f"{args.name}.srt"
    srt.write_text(_srt(cues), encoding="utf-8")
    meta = out_dir / "chapters.txt"
    lines = [";FFMETADATA1", "title=AI Study Companion - full tutorial", "artist=AI Study Companion", ""]
    for n, (start, title) in enumerate(chapters):
        end = chapters[n + 1][0] if n + 1 < len(chapters) else total
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(start * 1000)}", f"END={int(end * 1000)}", f"title={title}", ""]
    meta.write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "chapters.md").write_text("\n".join(f"{_stamp(t)} {title}" for t, title in chapters) + "\n", encoding="utf-8")

    # ---- video: scenes are encoded in parallel worker processes, then joined without re-encoding
    video = out_dir / "video.mp4"
    specs = []
    for n, sc in enumerate(scenes):
        prev_last = None
        if n > 0:
            prev = scenes[n - 1]
            pclip = clips[prev["id"]]
            prev_last = str(args.build / "frames" / prev["id"] / pclip.frame_at((n_frames[prev["id"]] - 1) / FPS))
        badge = chapter_no.get(sc["id"]) if sc.get("_chapter_start") and sc["kind"] != "slide" else None
        specs.append({"id": sc["id"], "n_frames": n_frames[sc["id"]], "badge": badge, "chapter": sc["_chapter"], "prev_last": prev_last})
    jobs = max(1, min(args.jobs, len(specs)))
    groups: list[list[dict]] = [[] for _ in range(jobs)]
    target = sum(sp["n_frames"] for sp in specs) / jobs
    k, filled = 0, 0
    for sp in specs:  # contiguous groups of roughly equal length
        if filled >= target * (k + 1) and k < jobs - 1 and groups[k]:
            k += 1
        groups[k].append(sp)
        filled += sp["n_frames"]
    groups = [g for g in groups if g]
    seg_dir = out_dir / "segments"
    seg_dir.mkdir(exist_ok=True)
    work = [{"build": str(args.build), "out": str(seg_dir / f"seg{i:02d}.mp4"), "scenes": g, "crf": args.crf, "preset": args.preset}
            for i, g in enumerate(groups)]
    started = time.time()
    if len(work) == 1:
        segments = [_encode_segment(work[0])]
    else:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=len(work)) as pool:
            segments = list(pool.map(_encode_segment, work))
    print(f"[assemble] {len(segments)} segment(s), {total / 60:.1f} min of video, encoded in {time.time() - started:.0f}s", flush=True)
    listing = seg_dir / "list.txt"
    listing.write_text("".join(f"file '{Path(sg).as_posix()}'\n" for sg in segments), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(video)], check=True)

    final = out_dir / f"{args.name}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(wav), "-i", str(srt), "-i", str(meta),
         "-map", "0:v", "-map", "1:a", "-map", "2:s", "-map_metadata", "3", "-map_chapters", "3",
         "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "160k",
         "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-metadata:s:a:0", "language=eng",
         "-movflags", "+faststart", "-shortest", str(final)],
        check=True,
    )
    print(f"wrote {final} ({final.stat().st_size / 1e6:.1f} MB, {total / 60:.1f} min) and {srt.name}")
    if args.preview_720:
        small = out_dir / f"{args.name}_720p.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(final), "-map", "0", "-vf", "scale=1280:-2:flags=lanczos",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-c:a", "copy", "-c:s", "copy", "-movflags", "+faststart", str(small)], check=True)
        print(f"wrote {small} ({small.stat().st_size / 1e6:.1f} MB)")


def _cues(text: str, start: float, duration: float, max_chars: int = 84) -> list[tuple[float, float, str]]:
    sentences: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        joined = len(sentences[-1]) + len(sentence) + 1 if sentences else 999
        if joined <= 70 or (sentences and len(sentences[-1]) < 16 and joined <= max_chars + 16):
            sentences[-1] = f"{sentences[-1]} {sentence}"  # keep short sentences together ("Done. 153 pages ...")
        else:
            sentences.append(sentence)
    parts: list[str] = []
    for sentence in sentences:
        n = max(1, -(-len(sentence) // max_chars))  # cues needed for this sentence
        target, chunk, made = len(sentence) / n, [], 0
        for w in sentence.split():
            chunk.append(w)
            if made < n - 1 and len(" ".join(chunk)) >= target:  # balanced, so no one-word leftovers
                parts.append(" ".join(chunk))
                chunk, made = [], made + 1
        if chunk:
            parts.append(" ".join(chunk))
    weights = [len(p) + 8 for p in parts]
    total_w, t, out = sum(weights), start, []
    for p, wgt in zip(parts, weights, strict=True):
        d = duration * wgt / total_w
        out.append((t, t + d, p))
        t += d
    return out


def _srt(cues: list[tuple[float, float, str]]) -> str:
    def ts(x: float) -> str:
        ms = int(round(x * 1000))
        return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    blocks = []
    for n, (a, b, text) in enumerate(cues, 1):
        wrapped = text if len(text) <= 42 else _wrap2(text)
        blocks.append(f"{n}\n{ts(a)} --> {ts(b)}\n{wrapped}\n")
    return "\n".join(blocks)


def _wrap2(text: str) -> str:
    words = text.split()
    best, best_diff = text, 10**9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if abs(len(a) - len(b)) < best_diff:
            best, best_diff = f"{a}\n{b}", abs(len(a) - len(b))
    return best


def _stamp(t: float) -> str:
    t = int(t)
    return f"{t // 60:02d}:{t % 60:02d}" if t < 3600 else f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}"


# ----------------------------------------------------------------------------- qa

def stage_qa(args: argparse.Namespace) -> None:
    """Contact sheet of every beat (frame at the middle of its narration) for a visual review."""
    from PIL import Image, ImageDraw

    script = load_script()
    tiles = []
    for s in script["scenes"]:
        tl_path = args.build / "timelines" / f"{s['id']}.json"
        if not tl_path.exists():
            continue
        clip = SceneClip(json.loads(tl_path.read_text(encoding="utf-8")))
        for beat in clip.tl["beats"]:
            u = clip.out(beat["t"]) + beat["duration"] * 0.6
            img = Image.open(args.build / "frames" / s["id"] / clip.frame_at(u)).convert("RGB").resize((480, 270))
            ImageDraw.Draw(img).text((8, 6), f"{s['id']}#{beat['index']}", fill=(255, 64, 64))
            tiles.append(img)
    cols = 6
    sheet = Image.new("RGB", (cols * 480, ((len(tiles) + cols - 1) // cols) * 270), "black")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 480, (i // cols) * 270))
    out = args.build / "out" / "contact_sheet.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=85)
    print(f"wrote {out} ({len(tiles)} beats)")


# ----------------------------------------------------------------------------- cli

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stage", choices=["tts", "record", "assemble", "qa", "all"])
    ap.add_argument("--build", type=Path, default=ROOT / "build" / "tutorial", help="working folder (gitignored)")
    ap.add_argument("--kokoro-dir", default=os.environ.get("KOKORO_DIR", "."), help="folder with kokoro-v1.0.onnx and voices-v1.0.bin")
    ap.add_argument("--model", default="gemini-3.5-flash-lite", help="model the Settings scene selects (Google Gemini)")
    ap.add_argument("--only", default="", help="comma-separated scene ids to record or assemble")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--retry-wait", type=float, default=20.0, help="seconds to wait before re-recording a failed scene")
    ap.add_argument("--name", default="AI_Study_Companion_Full_Tutorial")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)), help="parallel encoder processes for the assemble stage")
    ap.add_argument("--preview-720", action="store_true", help="also write a smaller 720p copy")
    args = ap.parse_args()
    args.build = args.build.resolve()
    args.build.mkdir(parents=True, exist_ok=True)
    stages = ["tts", "record", "assemble", "qa"] if args.stage == "all" else [args.stage]
    if "assemble" in stages and not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH; the assemble stage needs it (see scripts/tutorial/README.md)")
    for st in stages:
        {"tts": stage_tts, "record": stage_record, "assemble": stage_assemble, "qa": stage_qa}[st](args)


if __name__ == "__main__":
    sys.exit(main())
