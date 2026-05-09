import pytest
from starlette.requests import Request

from backend.api.endpoints.sms_webhook import (
    SENDER_FIELDS,
    TEXT_FIELDS,
    _first_payload_value,
    _parse_loose_sms_text,
    _parse_sms_payload,
    _payload_from_loaded_json,
)


def _request_with_body(body: bytes, content_type: str) -> Request:
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/sms/webhook",
            "headers": [(b"content-type", content_type.encode())],
            "query_string": b"key=secret",
        },
        receive,
    )


def test_loose_macrodroid_payload_extracts_message_and_sender():
    payload = _parse_loose_sms_text(
        "sender: HDFC-BK\n"
        "message: Rs.299.00 credited to A/c. UTR: 312456789012\n"
    )

    assert _first_payload_value(payload, SENDER_FIELDS) == "HDFC-BK"
    assert _first_payload_value(payload, TEXT_FIELDS) == (
        "Rs.299.00 credited to A/c. UTR: 312456789012"
    )


def test_loose_payload_without_known_message_field_keeps_raw_sms_text():
    raw = "VK-BANK\nRs.500 received via UPI Ref No: 777777777777"
    payload = _parse_loose_sms_text(raw)

    assert _first_payload_value(payload, TEXT_FIELDS) == raw


def test_json_array_payload_is_preserved_as_sms_text():
    payload = _payload_from_loaded_json(["sender: BANK", "Rs.10 UTR: 123456789012"])

    assert _first_payload_value(payload, TEXT_FIELDS) == (
        "sender: BANK\nRs.10 UTR: 123456789012"
    )


@pytest.mark.asyncio
async def test_malformed_json_content_type_falls_back_to_loose_sms_text():
    request = _request_with_body(
        b"sender: AX-BANK\nmessage: Rs.10 credited UTR: 123456789012",
        "application/json",
    )

    payload = await _parse_sms_payload(request)

    assert _first_payload_value(payload, SENDER_FIELDS) == "AX-BANK"
    assert _first_payload_value(payload, TEXT_FIELDS) == (
        "Rs.10 credited UTR: 123456789012"
    )
    assert "key" not in payload
