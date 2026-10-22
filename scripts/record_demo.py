#!/usr/bin/env python
"""Record the product walkthrough video with Playwright.

Drives the real app (backend serving the built frontend) through the full
study loop: sign up -> upload an open textbook -> ask the tutor -> inspect the
citations -> generate and take a quiz -> review results -> flashcards ->
summary -> concept map -> syllabus -> settings -> dashboard.

    python scripts/record_demo.py --base-url http://localhost:8000 --out docs/demo

Produces docs/demo/demo.webm (raw), then ffmpeg converts it to demo.mp4 and a
README-friendly demo.gif. Screenshots land in docs/demo/screenshots/.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "data" / "sample_notes"
VIEWPORT = {"width": 1440, "height": 900}

CAPTION_JS = """
(text) => {
  let el = document.getElementById('asc-demo-caption');
  if (!el) {
    el = document.createElement('div');
    el.id = 'asc-demo-caption';
    el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:99999;'
      + 'background:rgba(11,18,32,.92);color:#fff;padding:12px 20px;border-radius:14px;font:600 17px/1.3 "Plus Jakarta Sans",system-ui,sans-serif;'
      + 'box-shadow:0 12px 32px -12px rgba(0,0,0,.6);max-width:900px;text-align:center;pointer-events:none;transition:opacity .3s';
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.style.opacity = text ? '1' : '0';
}
"""


def caption(page: Page, text: str, pause: float = 1.2) -> None:
    page.evaluate(CAPTION_JS, text)
    time.sleep(pause)


def shot(page: Page, out: Path, name: str) -> None:
    (out / "screenshots").mkdir(parents=True, exist_ok=True)
    page.evaluate(CAPTION_JS, "")
    page.screenshot(path=str(out / "screenshots" / f"{name}.png"))


def type_slowly(page: Page, selector: str, text: str, delay: int = 18) -> None:
    page.click(selector)
    page.fill(selector, "")
    page.type(selector, text, delay=delay)


def run(base_url: str, out: Path, book: Path, email: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT, record_video_dir=str(out / ".raw"), record_video_size=VIEWPORT, device_scale_factor=1)
        page = context.new_page()
        page.set_default_timeout(60_000)

        # 1. Sign up ---------------------------------------------------------------
        page.goto(f"{base_url}/register")
        page.wait_for_selector("text=Create your study space")
        caption(page, "AI Study Companion: a RAG-powered personal tutor built around your own notes", 2.2)
        type_slowly(page, "input[autocomplete='name']", "Asha Verma")
        type_slowly(page, "input[type='email']", email)
        type_slowly(page, "input[type='password']", "demo-password-123", delay=8)
        shot(page, out, "01-signup")
        page.click("button:has-text('Create account')")
        page.wait_for_selector("text=Recommended next")
        caption(page, "A fresh account starts empty. Let's add real study material.", 1.8)

        # 2. Upload notes ----------------------------------------------------------
        page.click("a[href='/notes']")
        page.wait_for_selector("text=Drag notes here")
        caption(page, "Upload PDFs, Word files or text. Here: an open-licensed Database Design textbook (CC BY 4.0).", 1.5)
        page.fill("input[placeholder*='OS Unit 4']", "Database Design (Watt & Eng)")
        page.set_input_files("[data-testid='file-input']", str(book))
        page.wait_for_selector("text=Indexing", timeout=30_000)
        caption(page, "The file is parsed, split into ~500-token passages, embedded locally and indexed (keyword + vector).", 2.0)
        page.wait_for_selector("tr:has-text('Ready')", timeout=600_000)
        caption(page, "Indexed. Every passage keeps its page number for citations.", 1.5)
        shot(page, out, "02-notes-library")
        type_slowly(page, "input[placeholder*='page replacement']", "functional dependency and normal forms")
        page.keyboard.press("Enter")
        page.wait_for_selector("mark", timeout=30_000)
        caption(page, "Hybrid search: BM25 keyword hits (highlighted) fused with semantic matches.", 2.2)
        shot(page, out, "03-notes-search")

        # 3. Ask the tutor -------------------------------------------------------------
        page.click("a[href='/tutor']")
        page.wait_for_selector("text=Ask anything from your notes")
        caption(page, "Ask the tutor. Answers stream in and cite the exact passages they came from.", 1.5)
        type_slowly(page, "textarea", "Explain the difference between a primary key and a foreign key with an example", delay=10)
        page.keyboard.press("Enter")
        page.wait_for_selector("button:has-text('source')", timeout=120_000)
        page.wait_for_selector("text=Copy", timeout=120_000)
        time.sleep(1.0)
        caption(page, "Grounded answer with [n] citations, plus follow-up questions.", 2.0)
        shot(page, out, "04-tutor-answer")
        page.click("button:has-text('source')")
        page.wait_for_selector("text=Sources used in this answer")
        caption(page, "Each citation opens the source passage with its page and relevance score.", 2.2)
        shot(page, out, "05-tutor-sources")
        page.keyboard.press("Escape")
        follow = page.query_selector("button.rounded-full.border-brand-200")
        if follow:
            caption(page, "Follow-ups keep the conversation moving.", 1.0)
            follow.click()
            page.wait_for_selector("button:has-text('Copy') >> nth=1", timeout=120_000)
            time.sleep(1.0)

        # 4. Quiz -----------------------------------------------------------------------
        page.click("a[href='/quizzes']")
        page.wait_for_selector("text=Quizzes & Grading")
        page.click("button:has-text('New quiz')")
        page.wait_for_selector("text=Generate a quiz")
        caption(page, "Generate a quiz on any topic, grounded in the uploaded notes.", 1.2)
        page.fill("input[placeholder*='CPU scheduling']", "Normalization and functional dependencies")
        page.click("button:has-text('Database Design')")
        page.select_option("select >> nth=0", "5")
        shot(page, out, "06-quiz-generate")
        page.click("button:has-text('Generate quiz')")
        page.wait_for_selector("text=/Q1/", timeout=180_000)
        caption(page, "MCQ, true/false and short-answer questions with marks. Let's attempt it.", 1.5)
        shot(page, out, "07-quiz-attempt")
        for _ in range(12):
            if page.query_selector("button:has-text('Submit quiz')"):
                textarea = page.query_selector("textarea")
                if textarea:
                    textarea.fill("A relation is in 2NF when it is in 1NF and every non-key attribute depends on the whole primary key, removing partial dependencies.")
                else:
                    opts = page.query_selector_all("button.flex.w-full")
                    if opts:
                        opts[0].click()
                page.click("button:has-text('Submit quiz')")
                break
            textarea = page.query_selector("textarea")
            if textarea:
                textarea.fill("A relation is in 2NF when it is in 1NF and every non-key attribute depends on the whole primary key, removing partial dependencies.")
            else:
                opts = page.query_selector_all("button.flex.w-full")
                if opts:
                    opts[0].click()
            page.click("button:has-text('Next')")
            time.sleep(0.6)
        page.wait_for_selector("text=Topic breakdown, text=Retake", timeout=180_000)
        page.wait_for_selector("button:has-text('Retake')", timeout=180_000)
        caption(page, "Objective questions are auto-graded; descriptive answers are graded against a rubric with feedback.", 2.5)
        shot(page, out, "08-quiz-result")

        # 5. Flashcards ---------------------------------------------------------------------
        page.goto(f"{base_url}/revision?tab=flashcards")
        page.wait_for_selector("text=New deck from notes")
        page.click("button:has-text('New deck from notes')")
        page.wait_for_selector("text=Generate flashcards")
        page.fill("input[placeholder*='Deadlock']", "Entity relationship model")
        page.click("button:has-text('Database Design')")
        caption(page, "Flashcards are generated from the notes and scheduled with SM-2 spaced repetition.", 1.0)
        page.click("button:has-text('Create deck')")
        page.wait_for_selector("button:has-text('Review all due')", timeout=180_000)
        page.wait_for_selector("text=due", timeout=30_000)
        shot(page, out, "09-flashcards")
        page.click("button:has-text('Review all due')")
        page.wait_for_selector("text=Click or press space to reveal")
        time.sleep(1.0)
        page.keyboard.press("Space")
        time.sleep(1.0)
        caption(page, "Rate each card: Again, Hard, Good or Easy. Intervals adapt to you.", 1.4)
        page.click("button:has-text('Good')")
        time.sleep(0.8)
        page.keyboard.press("Space")
        time.sleep(0.6)
        page.click("button:has-text('Easy')")
        time.sleep(0.6)

        # 6. Summary + concept map -------------------------------------------------------
        page.goto(f"{base_url}/revision?tab=summaries")
        page.click("button:has-text('New summary')")
        page.fill("input[placeholder*='Deadlock']", "Normalization")
        page.click("button:has-text('Database Design')")
        page.click("button:has-text('Summarise')")
        page.wait_for_selector("text=60-second revision", timeout=180_000)
        caption(page, "Exam-style summaries: definition, core concepts, formulas, keywords, common mistakes.", 2.2)
        shot(page, out, "10-summary")
        page.goto(f"{base_url}/revision?tab=maps")
        page.click("button:has-text('New concept map')")
        page.fill("input[placeholder*='Deadlock']", "Relational model")
        page.click("button:has-text('Database Design')")
        page.click("button:has-text('Build map')")
        page.wait_for_selector(".react-flow__node", timeout=180_000)
        time.sleep(1.5)
        caption(page, "Interactive concept maps and flowcharts rendered with React Flow.", 2.2)
        shot(page, out, "11-concept-map")

        # 7. Syllabus + lectures + settings ------------------------------------------------
        page.click("a[href='/syllabus']")
        page.wait_for_selector("text=Semester 3")
        caption(page, "The AKTU syllabus is built in: track topics per unit, and jump to quiz, cards or lectures for any unit.", 2.0)
        page.click("text=Database Management System")
        page.wait_for_selector("text=Unit 1")
        page.click("input[type='checkbox'] >> nth=0")
        page.click("input[type='checkbox'] >> nth=1")
        time.sleep(0.8)
        shot(page, out, "12-syllabus")
        page.click("a[href='/settings']")
        page.wait_for_selector("text=Choose a provider")
        caption(page, "Bring your own model: Groq, Gemini, OpenAI, Claude, Grok, OpenRouter, Mistral, DeepSeek or a local Ollama.", 2.4)
        shot(page, out, "13-settings")

        # 8. Dashboard --------------------------------------------------------------------
        page.click("a[href='/']")
        page.wait_for_selector("text=Accuracy by topic")
        time.sleep(1.0)
        caption(page, "The dashboard tracks accuracy by topic, streaks, cards due and what to do next.", 2.6)
        shot(page, out, "14-dashboard")
        caption(page, "Open source. github.com/sachincse/ai-study-companion", 2.5)

        context.close()
        browser.close()
    raw = next((out / ".raw").glob("*.webm"))
    target = out / "demo.webm"
    shutil.move(str(raw), target)
    shutil.rmtree(out / ".raw", ignore_errors=True)
    return target


def convert(webm: Path) -> None:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found; keeping webm only")
        return
    mp4 = webm.with_suffix(".mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "23", "-movflags", "+faststart", str(mp4)], check=True)
    gif = webm.with_suffix(".gif")
    palette = webm.parent / "palette.png"
    filters = "fps=8,scale=960:-1:flags=lanczos"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf", f"{filters},palettegen=max_colors=128", str(palette)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-i", str(palette), "-lavfi", f"{filters} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5", str(gif)], check=True)
    palette.unlink(missing_ok=True)
    print(f"wrote {mp4} ({mp4.stat().st_size / 1e6:.1f} MB) and {gif} ({gif.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--out", default=str(ROOT / "docs" / "demo"))
    ap.add_argument("--book", default=str(NOTES / "Database_Design_2nd_Edition_(Watt_Eng)_CC-BY-4.0.pdf"))
    ap.add_argument("--email", default=f"asha.demo{int(time.time())}@example.com")
    args = ap.parse_args()
    video = run(args.base_url, Path(args.out), Path(args.book), args.email)
    print(f"recorded {video}")
    convert(video)
