"""Background ingestion scheduling.

In normal operation documents are processed by FastAPI's background task pool
after the upload response is returned. In the test environment (``APP_ENV=test``)
processing happens inline so tests stay deterministic.
"""
from __future__ import annotations

from fastapi import BackgroundTasks

from app.core.config import get_settings
from app.services.document_service import process_document


def schedule_ingestion(background: BackgroundTasks, document_id: int) -> None:
    if get_settings().app_env == "test":
        process_document(document_id)
        return
    background.add_task(process_document, document_id)
