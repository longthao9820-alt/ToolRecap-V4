"""Tests for GatewayClient."""

import base64
import json
from pathlib import Path
import tracemalloc

import httpx
import pytest

from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.errors import (
    CancelledError,
    GatewayError,
    GatewayResponseError,
    InvalidGatewayResponseError,
    ModelCapabilityError,
    UnsupportedMediaError,
)
from toolrecap_v4.gateway import GatewayClient, StreamingChatPayload, extract_json_from_text


def create_dummy_video(path: Path, size_bytes: int = 1024) -> Path:
    path.write_bytes(b"\x00" * size_bytes)
    return path


def test_ordered_multi_source_payload_and_exact_prompt(tmp_path: Path):
    """Verify ordered multi-source payload in ONE request and exact unchanged prompt."""
    v1 = create_dummy_video(tmp_path / "ep01.mp4", 100)
    v2 = create_dummy_video(tmp_path / "ep02.mkv", 200)

    captured_payload = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={"data": [{"id": "ag/gemini-3.8-flash", "capabilities": {"videoInput": True}}]},
            )
        if request.url.path == "/v1/chat/completions":
            captured_payload = json.loads(request.read())
            # Return valid JSON inside assistant content
            sse_body = (
                'data: {"choices": [{"delta": {"content": "```json\\n{\\"recap\\": \\"ok\\"}\\n```"}}]}\n\n'
                "data: [DONE]\n\n"
            )
            return httpx.Response(200, text=sse_body, headers={"Content-Type": "text/event-stream"})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gw = GatewayClient(client=client)

    exact_prompt = "DO NOT MODIFY THIS PROMPT: summarize character arcs exactly as directed."
    tech_schema = {"schema_version": "3.0"}
    source_meta = [{"source_file": "ep01.mp4"}, {"source_file": "ep02.mkv"}]

    result = gw.submit_chat_analysis(
        sources=[v1, v2],
        prompt=exact_prompt,
        model="ag/gemini-3.8-flash",
        technical_schema=tech_schema,
        source_metadata=source_meta,
        stream=True,
    )

    assert result.parsed_json == {"recap": "ok"}
    assert captured_payload is not None
    assert captured_payload["model"] == "ag/gemini-3.8-flash"

    messages = captured_payload["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"

    content = messages[0]["content"]
    # 1. Prompt is EXACT and UNCHANGED
    assert content[0]["type"] == "text"
    assert content[0]["text"] == exact_prompt

    # 2. Technical schema & metadata sent SEPARATELY
    assert content[1]["type"] == "text"
    assert "Technical Schema & Source Metadata" in content[1]["text"]
    assert "schema_version" in content[1]["text"]

    # 3. Both ordered sources sent in ONE request with verified image_url data video URIs
    assert content[2]["type"] == "image_url"
    assert content[2]["image_url"]["url"].startswith("data:video/mp4;base64,")
    assert content[3]["type"] == "image_url"
    assert content[3]["image_url"]["url"].startswith("data:video/x-matroska;base64,")


def test_zero_preprocessing_rejection(tmp_path: Path):
    """Verify unsupported containers and size violations fail without preprocessing."""
    gw = GatewayClient(max_file_size_bytes=500)

    # Unsupported format
    unsupported = tmp_path / "bad.flv"
    unsupported.write_bytes(b"12345")
    with pytest.raises(UnsupportedMediaError, match="Unsupported media container"):
        gw.submit_chat_analysis([unsupported], prompt="Test", validate_capability=False)

    # Empty file (0 bytes)
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(UnsupportedMediaError, match="empty .*0 bytes"):
        gw.submit_chat_analysis([empty], prompt="Test", validate_capability=False)

    # Exceeding size limit
    oversized = tmp_path / "large.mp4"
    oversized.write_bytes(b"X" * 1000)
    with pytest.raises(UnsupportedMediaError, match="exceeds maximum limit"):
        gw.submit_chat_analysis([oversized], prompt="Test", validate_capability=False)


def test_model_capability_validation():
    """Verify Gateway validates advertised videoInput capability."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "video-model", "capabilities": {"videoInput": True}},
                    {"id": "text-only-model", "capabilities": {"videoInput": False}},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gw = GatewayClient(client=client)

    # Video model passes
    assert gw.validate_model_video_capability("video-model") is True

    # Text-only model fails
    with pytest.raises(ModelCapabilityError, match="does not advertise 'videoInput'"):
        gw.validate_model_video_capability("text-only-model")

    # Missing model fails
    with pytest.raises(ModelCapabilityError, match="not found"):
        gw.validate_model_video_capability("unknown-model")


def test_transient_vs_logical_retry(tmp_path: Path):
    """Verify transient errors are retried while logical errors fail immediately."""
    v = create_dummy_video(tmp_path / "test.mp4", 100)

    transient_attempts = 0

    def transient_handler(request: httpx.Request) -> httpx.Response:
        nonlocal transient_attempts
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m", "capabilities": {"videoInput": True}}]})
        transient_attempts += 1
        if transient_attempts < 3:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(
            200,
            text='data: {"choices": [{"delta": {"content": "{\\"status\\": \\"ok\\"}"}}]}\n\ndata: [DONE]\n\n',
            headers={"Content-Type": "text/event-stream"},
        )

    client = httpx.Client(transport=httpx.MockTransport(transient_handler))
    gw = GatewayClient(client=client, max_retries=3, backoff_factor=0.01)
    res = gw.submit_chat_analysis([v], prompt="Prompt", model="m")
    assert res.parsed_json == {"status": "ok"}
    assert transient_attempts == 3

    # Logical error (400) fails immediately
    logical_attempts = 0

    def logical_handler(request: httpx.Request) -> httpx.Response:
        nonlocal logical_attempts
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m", "capabilities": {"videoInput": True}}]})
        logical_attempts += 1
        return httpx.Response(400, text="Bad Request: payload schema invalid")

    client2 = httpx.Client(transport=httpx.MockTransport(logical_handler))
    gw2 = GatewayClient(client=client2, max_retries=3, backoff_factor=0.01)
    with pytest.raises(GatewayResponseError, match="HTTP 400"):
        gw2.submit_chat_analysis([v], prompt="Prompt", model="m")
    assert logical_attempts == 1


def test_cancellation(tmp_path: Path):
    """Verify cancellation token stops Gateway streaming and raises CancelledError."""
    v = create_dummy_video(tmp_path / "test.mp4", 100)
    token = CancellationToken()
    token.cancel()

    gw = GatewayClient()
    with pytest.raises(CancelledError):
        gw.submit_chat_analysis([v], prompt="Prompt", cancellation_token=token, validate_capability=False)


def test_no_repair_on_invalid_json():
    """Verify Gateway raw sanitized response and failure without automatic repair."""
    # Valid JSON in code block
    valid_text = "Here is the response:\n```json\n{\"outputs\": [1, 2, 3]}\n```"
    parsed = extract_json_from_text(valid_text)
    assert parsed == {"outputs": [1, 2, 3]}

    # Broken JSON must NOT be repaired
    broken_text = "```json\n{\"outputs\": [1, 2, 3, broken]}\n```"
    with pytest.raises(InvalidGatewayResponseError, match="Automatic repair is strictly prohibited"):
        extract_json_from_text(broken_text)


class StreamingMockTransport(httpx.BaseTransport):
    """Transport that delivers the request without calling request.read() to preserve streaming."""

    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_small_byte_integrity(tmp_path: Path):
    """Verify byte-for-byte base64 integrity and Content-Length accuracy across small files."""
    sizes_and_data = [
        (1, b"\x01"),
        (2, b"\x02\x03"),
        (3, b"\x04\x05\x06"),
        (4, b"\x07\x08\x09\x0a"),
        (17, bytes(range(17))),
        (65536, b"B" * 65536),
    ]
    files = []
    for i, (sz, data) in enumerate(sizes_and_data):
        p = tmp_path / f"test_{i}_{sz}b.mp4"
        p.write_bytes(data)
        files.append((p, data))

    captured_body = bytearray()
    content_length_header = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal content_length_header
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m", "capabilities": {"videoInput": True}}]})
        if request.url.path == "/v1/chat/completions":
            content_length_header = int(request.headers["Content-Length"])
            for chunk in request.stream:
                captured_body.extend(chunk)
            sse_body = 'data: {"choices": [{"delta": {"content": "{\\"status\\": \\"ok\\"}"}}]}\n\ndata: [DONE]\n\n'
            return httpx.Response(200, text=sse_body, headers={"Content-Type": "text/event-stream"})
        return httpx.Response(404)

    client = httpx.Client(transport=StreamingMockTransport(handler))
    gw = GatewayClient(client=client)

    res = gw.submit_chat_analysis(
        sources=[p for p, _ in files],
        prompt="verify integrity",
        model="m",
        technical_schema={"schema": "v1"},
        source_metadata=[{"name": p.name} for p, _ in files],
    )

    assert res.parsed_json == {"status": "ok"}
    assert content_length_header == len(captured_body)

    # Parse body and verify exact byte integrity
    parsed_req = json.loads(captured_body.decode("utf-8"))
    content_parts = parsed_req["messages"][0]["content"]

    # content[0] is prompt, content[1] is technical schema & metadata
    assert content_parts[0]["text"] == "verify integrity"
    assert "Technical Schema & Source Metadata" in content_parts[1]["text"]

    # Each source must match original bytes exactly
    for idx, (p, orig_data) in enumerate(files):
        media_part = content_parts[2 + idx]
        assert media_part["type"] == "image_url"
        url = media_part["image_url"]["url"]
        assert url.startswith("data:video/mp4;base64,")
        b64_str = url.split("base64,", 1)[1]
        decoded_bytes = base64.b64decode(b64_str)
        assert decoded_bytes == orig_data, f"Byte mismatch at index {idx} (size {len(orig_data)})"


def test_streaming_550mb_sparse_fixture_bounded_memory(tmp_path: Path):
    """Verify >500MB sparse file streams with bounded memory (peak < 5MB) and default None limit."""
    sparse_path = tmp_path / "large_sparse_550mb.mp4"
    sparse_size = 550 * 1024 * 1024  # 550 MB
    with open(sparse_path, "wb") as f:
        f.seek(sparse_size - 1)
        f.write(b"\x01")

    assert sparse_path.stat().st_size == sparse_size

    total_streamed_bytes = 0
    content_length_header = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal total_streamed_bytes, content_length_header
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "video-model", "capabilities": {"videoInput": True}}]})
        if request.url.path == "/v1/chat/completions":
            content_length_header = int(request.headers["Content-Length"])
            for chunk in request.stream:
                total_streamed_bytes += len(chunk)
            sse_body = 'data: {"choices": [{"delta": {"content": "{\\"status\\": \\"success\\"}"}}]}\n\ndata: [DONE]\n\n'
            return httpx.Response(200, text=sse_body, headers={"Content-Type": "text/event-stream"})
        return httpx.Response(404)

    client = httpx.Client(transport=StreamingMockTransport(handler))
    gw = GatewayClient(client=client)

    # Invariant: default max_file_size_bytes is None (500MB reject limit removed)
    assert gw.max_file_size_bytes is None

    tracemalloc.start()
    res = gw.submit_chat_analysis(
        sources=[sparse_path],
        prompt="process 550mb sparse file",
        model="video-model",
    )
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert res.parsed_json == {"status": "success"}
    assert content_length_header == total_streamed_bytes
    assert total_streamed_bytes > sparse_size  # includes base64 expansion and JSON envelope

    # Memory must be bounded (well under 5MB, observed ~0.3MB)
    assert peak_memory < 5 * 1024 * 1024, f"Peak memory {peak_memory} exceeded 5 MB threshold"


def test_streaming_retry_reusable_fresh_iterator(tmp_path: Path):
    """Verify StreamingChatPayload can be iterated across multiple retry attempts."""
    v = create_dummy_video(tmp_path / "retry_test.mp4", 1024)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m", "capabilities": {"videoInput": True}}]})
        attempts += 1
        body = b"".join(request.stream)
        assert len(body) > 1024
        if attempts == 1:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(
            200,
            text='data: {"choices": [{"delta": {"content": "{\\"status\\": \\"retry_ok\\"}"}}]}\n\ndata: [DONE]\n\n',
            headers={"Content-Type": "text/event-stream"},
        )

    client = httpx.Client(transport=StreamingMockTransport(handler))
    gw = GatewayClient(client=client, max_retries=2, backoff_factor=0.01)

    res = gw.submit_chat_analysis([v], prompt="test retry", model="m")
    assert res.parsed_json == {"status": "retry_ok"}
    assert attempts == 2


def test_streaming_cancellation_mid_stream(tmp_path: Path):
    """Verify cancelling CancellationToken while generator streams raises CancelledError."""
    v = create_dummy_video(tmp_path / "cancel_test.mp4", 200000)
    token = CancellationToken()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m", "capabilities": {"videoInput": True}}]})
        # Cancel after consuming first chunk
        for chunk in request.stream:
            token.cancel()
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=StreamingMockTransport(handler))
    gw = GatewayClient(client=client)

    with pytest.raises(CancelledError):
        gw.submit_chat_analysis([v], prompt="test cancel", model="m", cancellation_token=token)


def test_owned_httpx_client_closed(monkeypatch):
    """Verify owned httpx.Client is closed in finally block when client is None."""
    closed = False
    original_client_init = httpx.Client.__init__
    original_client_close = httpx.Client.close

    def mock_close(self):
        nonlocal closed
        closed = True
        return original_client_close(self)

    monkeypatch.setattr(httpx.Client, "close", mock_close)

    def mock_send(self, request, **kwargs):
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m", "capabilities": {"videoInput": True}}]})
        return httpx.Response(
            200,
            text='data: {"choices": [{"delta": {"content": "{\\"status\\": \\"ok\\"}"}}]}\n\ndata: [DONE]\n\n',
            headers={"Content-Type": "text/event-stream"},
        )

    monkeypatch.setattr(httpx.Client, "send", mock_send)

    gw = GatewayClient()  # client=None, owns internal client
    assert gw._external_client is None

    # validate_model_video_capability closes owned client
    gw.validate_model_video_capability("m")
    assert closed is True


def test_stream_object_and_dict_payload_acceptance(tmp_path: Path):
    """Verify _execute_streaming_request and _execute_sync_request accept stream object and dict."""
    v = create_dummy_video(tmp_path / "test.mp4", 100)
    payload_obj = StreamingChatPayload(sources=[v], prompt="test")
    payload_dict = {"model": "m", "messages": [{"role": "user", "content": "hello"}]}

    captured_content_type = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_content_type.append(request.headers.get("Content-Type"))
        if "/stream" in request.url.path:
            return httpx.Response(
                200,
                text='data: {"choices": [{"delta": {"content": "streamed"}}]}\n\ndata: [DONE]\n\n',
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "synced"}}]},
        )

    client = httpx.Client(transport=StreamingMockTransport(handler))
    gw = GatewayClient(client=client)

    # 1. Stream request with StreamingChatPayload
    text1, _ = gw._execute_streaming_request(client, "http://test/stream", payload_obj, {}, None)
    assert text1 == "streamed"

    # 2. Stream request with dict
    text2, _ = gw._execute_streaming_request(client, "http://test/stream", payload_dict, {}, None)
    assert text2 == "streamed"

    # 3. Sync request with StreamingChatPayload
    text3, _ = gw._execute_sync_request(client, "http://test/sync", payload_obj, {}, None)
    assert text3 == "synced"

    # 4. Sync request with dict
    text4, _ = gw._execute_sync_request(client, "http://test/sync", payload_dict, {}, None)
    assert text4 == "synced"

