"""
Smoke test: WhatsApp bot booking flow.

Verifies that POST /webhook with a valid Meta payload returns HTTP 200
with body {"status": "success"}.

Task 6.1 — Validates: Requirements 6.1, 6.2
"""
import os
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# Helper: run async coroutine from sync context
# ---------------------------------------------------------------------------

def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Valid Meta webhook payload (from Pydantic models in main.py)
# ---------------------------------------------------------------------------

VALID_WEBHOOK_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "123",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "1234567890",
                            "phone_number_id": "123",
                        },
                        "contacts": [
                            {
                                "profile": {"name": "Test User"},
                                "wa_id": "919999999999",
                            }
                        ],
                        "messages": [
                            {
                                "from": "919999999999",
                                "type": "text",
                                "text": {"body": "hello"},
                            }
                        ],
                    },
                }
            ],
        }
    ],
}


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def test_webhook_returns_success():
    """
    POST /webhook with a valid Meta payload must return HTTP 200
    with body {"status": "success"}.

    process_whatsapp_logic is patched to a no-op to avoid real DB/API calls.
    start_scheduler and stop_scheduler are patched to avoid APScheduler issues.
    """
    env_patch = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "META_PHONE_ID": "test_phone_id",
        "META_ACCESS_TOKEN": "test_access_token",
    }

    async def _noop_process(*args, **kwargs):
        pass

    def _noop_start():
        pass

    def _noop_stop():
        pass

    with patch.dict(os.environ, env_patch):
        with patch("app.main.process_whatsapp_logic", new=_noop_process):
            with patch("app.main.start_scheduler", new=_noop_start):
                with patch("app.main.stop_scheduler", new=_noop_stop):
                    from app.main import app as fastapi_app

                    with TestClient(fastapi_app, raise_server_exceptions=True) as client:
                        response = client.post("/webhook", json=VALID_WEBHOOK_PAYLOAD)

    assert response.status_code == 200, (
        f"Expected HTTP 200, got {response.status_code}: {response.text}"
    )
    assert response.json() == {"status": "success"}, (
        f"Expected {{'status': 'success'}}, got {response.json()}"
    )


def test_webhook_no_messages_returns_success():
    """
    POST /webhook with a payload that has no messages still returns
    HTTP 200 {"status": "success"} — the endpoint is always optimistic.
    """
    payload_no_messages = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "1234567890",
                                "phone_number_id": "123",
                            },
                        },
                    }
                ],
            }
        ],
    }

    env_patch = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "META_PHONE_ID": "test_phone_id",
        "META_ACCESS_TOKEN": "test_access_token",
    }

    def _noop_start():
        pass

    def _noop_stop():
        pass

    with patch.dict(os.environ, env_patch):
        with patch("app.main.start_scheduler", new=_noop_start):
            with patch("app.main.stop_scheduler", new=_noop_stop):
                from app.main import app as fastapi_app

                with TestClient(fastapi_app, raise_server_exceptions=True) as client:
                    response = client.post("/webhook", json=payload_no_messages)

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
