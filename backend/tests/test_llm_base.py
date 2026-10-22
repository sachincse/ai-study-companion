import pytest

from app.services.llm.base import ThinkTagFilter, extract_json


def test_extract_json_handles_fences_prose_and_trailing_commas():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here you go: {"a": [1, 2,], "b": "x",} thanks') == {"a": [1, 2], "b": "x"}
    assert extract_json("[1, 2, 3]") == [1, 2, 3]
    assert extract_json('<think>reasoning</think>{"ok": true}') == {"ok": True}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_think_filter_strips_reasoning_across_token_boundaries():
    f = ThinkTagFilter()
    tokens = ["<thi", "nk>secret ", "stuff</thi", "nk>visible ", "answer <b>bold</b>"]
    out = "".join(f.feed(t) for t in tokens) + f.flush()
    assert out == "visible answer <b>bold</b>"


def test_think_filter_passes_plain_text_untouched():
    f = ThinkTagFilter()
    out = "".join(f.feed(t) for t in ["Hello ", "world", "!"]) + f.flush()
    assert out == "Hello world!"


def test_follow_up_cleaning_drops_placeholders():
    from app.services.rag_service import clean_follow_ups

    cleaned = clean_follow_ups(["...", "<question 1>", "What is a TLB?", "What is a TLB?", "Compare paging and segmentation?"])
    assert cleaned == ["What is a TLB?", "Compare paging and segmentation?"]
    assert clean_follow_ups(None) == []
