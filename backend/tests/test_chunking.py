from app.services.chunking import ChunkingConfig, PageText, chunk_pages, chunk_text, clean_text, detect_heading


def test_chunks_respect_size_and_keep_pages():
    pages = [
        PageText(page_no=i, text=f"UNIT {i} INTRODUCTION\n" + " ".join(f"Sentence number {j} on page {i}." for j in range(60)))
        for i in range(1, 4)
    ]
    cfg = ChunkingConfig(chunk_size=800, chunk_overlap=100)
    chunks = chunk_pages(pages, cfg)
    assert len(chunks) >= 3
    assert all(len(c.content) <= cfg.chunk_size for c in chunks)
    assert chunks[0].page_no == 1
    assert chunks[-1].page_no == 3
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(c.token_estimate > 0 for c in chunks)


def test_overlap_carries_text_between_neighbours():
    text = " ".join(f"word{i}" for i in range(600))
    chunks = chunk_text(text, ChunkingConfig(chunk_size=500, chunk_overlap=120))
    assert len(chunks) > 2
    first_tail = chunks[0].content[-40:].split(" ")[1]
    assert first_tail in chunks[1].content


def test_headings_are_detected_and_inherited():
    pages = [PageText(page_no=1, text="# Deadlock\n" + ("Deadlock occurs when processes wait forever. " * 90))]
    chunks = chunk_pages(pages, ChunkingConfig(chunk_size=600, chunk_overlap=50))
    assert chunks[0].heading == "Deadlock"
    assert all(c.heading == "Deadlock" for c in chunks)
    assert detect_heading("Unit 3: CPU Scheduling\nmore text") == "Unit 3: CPU Scheduling"
    assert detect_heading("this is a normal sentence that is quite long and not a heading at all ok") is None


def test_clean_text_dehyphenates_and_collapses_whitespace():
    raw = "seg-\nmentation   is\r\nuseful\n\n\n\nvery"
    assert clean_text(raw) == "segmentation is\nuseful\n\nvery"


def test_empty_input_returns_no_chunks():
    assert chunk_pages([PageText(page_no=1, text="   \n ")]) == []
