"""Regression tests for DL.dl_callback's handling of API-path document payloads.

TR is migrating timeline documents from a plain URL string payload to an object
payload. pytr cannot download those yet and deliberately skips them with a warning.

The bug this guards: that warning interpolated ``payload["path"]`` unconditionally, so
a payload object without a ``path`` key raised KeyError *while building the message
that says we cannot download it*. dl_callback runs inside
``Timeline.process_timelineDetail``, so the KeyError escaped into the asyncio timeline
loop and aborted the whole ``dl_docs`` run -- every event lost, exit code 1, because of
one document nobody asked for.
"""

import logging

from pytr.dl import DL


def _callback_only_dl():
    """A DL with just the attributes dl_callback touches.

    __init__ opens a websession, a thread pool and the history file, none of which this
    code path needs, so bypass it rather than stand up that machinery in a unit test.
    """
    dl = DL.__new__(DL)
    dl.log = logging.getLogger("test-dl")
    dl.events_with_docs = []
    dl.events_without_docs = []
    return dl


def _event_with_document_payload(payload):
    return {
        "id": "evt-1",
        "title": "Kauforder",
        "subtitle": "Ausgeführt",
        "eventType": "TRADING_TRADE_EXECUTED",
        "timestamp": "2026-08-05T12:00:00.000+0000",
        "details": {
            "sections": [
                {
                    "type": "documents",
                    "title": "Dokumente",
                    "data": [{"id": "doc-1", "title": "Abrechnung", "action": {"payload": payload}}],
                }
            ]
        },
    }


def test_api_path_payload_without_path_key_does_not_raise(caplog):
    """The payload shape that broke the 2026-08-05 run: an object with no "path"."""
    dl = _callback_only_dl()
    event = _event_with_document_payload({"title": "Herunterladen", "shareable": True})

    with caplog.at_level(logging.WARNING):
        dl.dl_callback(event)

    assert event in dl.events_without_docs
    assert event not in dl.events_with_docs
    assert any("is not possible" in r.message for r in caplog.records)


def test_api_path_payload_with_path_key_is_reported_and_skipped(caplog):
    dl = _callback_only_dl()
    path = "api/v1/card/transactions/timelineDocuments/b9641cbc"
    event = _event_with_document_payload({"path": path, "title": "Herunterladen", "shareable": True})

    with caplog.at_level(logging.WARNING):
        dl.dl_callback(event)

    assert event in dl.events_without_docs
    assert any(path in r.message for r in caplog.records)


def test_string_payload_still_reaches_the_downloader():
    """The normal path must be untouched: a plain URL payload is handed to dl_doc."""
    dl = _callback_only_dl()
    calls = []
    dl.dl_doc = lambda doc, title, subfolder, date: calls.append(doc["id"])
    event = _event_with_document_payload("https://api.traderepublic.com/some/doc.pdf")

    dl.dl_callback(event)

    assert calls == ["doc-1"]
    assert event in dl.events_with_docs
