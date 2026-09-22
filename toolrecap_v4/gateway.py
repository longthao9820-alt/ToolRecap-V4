"""GatewayClient for 9router AI Gateway.

Invariants:
- Sends original bytes for ALL ordered sources in ONE chat request using verified image_url data video URI.
- User prompt remains completely unchanged; technical schema/source metadata sent separately.
- Validates advertised model video capability; explicit supported media/size limits fail without preprocessing.
- Configured API route (/v1/chat/completions), never guessed upload routes.
- Returns raw sanitized response and parsed JSON without editorial repair.
- Finite cancel-aware streaming networking; retries bounded to transient errors only.
- Credential leakage strictly prevented across all exceptions and outputs.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import mimetypes
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import httpx

from toolrecap_v4.cancellation import CancellationToken
from toolrecap_v4.errors import (
    CancelledError,
    GatewayError,
    GatewayResponseError,
    InvalidGatewayResponseError,
    ModelCapabilityError,
    UnsupportedMediaError,
)

TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
    ".avi": "video/x-msvideo",
    ".ts": "video/mp2t",
    ".m2ts": "video/mp2t",
    ".webm": "video/webm",
}

DEFAULT_MAX_FILE_SIZE_BYTES: Optional[int] = None  # None by default (no 500 MB limit)
DEFAULT_CHUNK_SIZE = 65535  # Divisible by 3 (65535 // 3 = 21845) for unpadded base64 streaming


class StreamingChatPayload:
    """Streamable JSON payload for chat completions with embedded base64 video media.

    Streams the full JSON request body in chunks without loading entire files into RAM.
    Chunks are read in sizes divisible by 3 (default 65535 bytes) so that intermediate
    base64 chunks require no padding and concatenate into valid base64 data.
    """

    def __init__(
        self,
        sources: Sequence[Union[Path, str, Tuple[Path, str, int]]],
        prompt: str,
        model: str = "ag/gemini-3.8-flash",
        stream: bool = True,
        technical_schema: Optional[Union[Dict[str, Any], str]] = None,
        source_metadata: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional[CancellationToken] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        reasoning_effort: Optional[str] = None,
    ) -> None:
        if chunk_size <= 0 or chunk_size % 3 != 0:
            raise ValueError(f"chunk_size must be positive and divisible by 3, got {chunk_size}")

        self.prompt = prompt
        self.model = model
        self.stream = stream
        self.technical_schema = technical_schema
        self.source_metadata = source_metadata
        self.cancellation_token = cancellation_token
        self.chunk_size = chunk_size
        self.reasoning_effort = reasoning_effort.strip().lower() if reasoning_effort and reasoning_effort.strip() else None

        # Normalize sources to (Path, mime_type, file_size)
        self.sources: List[Tuple[Path, str, int]] = []
        for s in sources:
            if isinstance(s, tuple) and len(s) == 3:
                p, m, sz = s
                self.sources.append((Path(p).resolve(), m, sz))
            else:
                p = Path(s).resolve()
                ext = p.suffix.lower()
                m = SUPPORTED_VIDEO_EXTENSIONS.get(ext, "application/octet-stream")
                sz = p.stat().st_size
                self.sources.append((p, m, sz))

        # Static JSON head
        payload_data: Dict[str, Any] = {"model": self.model, "stream": self.stream}
        if self.reasoning_effort:
            payload_data["reasoning_effort"] = self.reasoning_effort
        prefix_json = json.dumps(payload_data, ensure_ascii=False)
        self._head_bytes = (prefix_json[:-1] + ', "messages": [{"role": "user", "content": [').encode("utf-8")
        self._prompt_bytes = json.dumps({"type": "text", "text": self.prompt}, ensure_ascii=False).encode("utf-8")

        tech_meta: Dict[str, Any] = {}
        if self.technical_schema is not None:
            tech_meta["schema"] = self.technical_schema
        if self.source_metadata is not None:
            tech_meta["sources"] = self.source_metadata

        if tech_meta:
            self._tech_meta_bytes = (b"," + json.dumps({
                "type": "text",
                "text": f"Technical Schema & Source Metadata:\n{json.dumps(tech_meta, indent=2, ensure_ascii=False)}"
            }, ensure_ascii=False).encode("utf-8"))
        else:
            self._tech_meta_bytes = b""

        self._tail_bytes = b"]}]}"

        # Precompute exact Content-Length without loading files into memory
        total = len(self._head_bytes) + len(self._prompt_bytes) + len(self._tech_meta_bytes)
        self._source_frames: List[Tuple[Path, bytes, bytes]] = []

        for path, mime_type, size in self.sources:
            prefix = b',{"type": "image_url", "image_url": {"url": "data:' + mime_type.encode("ascii") + b';base64,'
            suffix = b'"}}'
            b64_len = ((size + 2) // 3) * 4 if size > 0 else 0
            total += len(prefix) + b64_len + len(suffix)
            self._source_frames.append((path, prefix, suffix))

        total += len(self._tail_bytes)
        self._content_length = total

    @property
    def content_length(self) -> int:
        """Exact precomputed Content-Length in bytes."""
        return self._content_length

    def __len__(self) -> int:
        return self._content_length

    def __iter__(self):
        """Yield JSON chunks with cancel checks. Reusable for request retries."""
        if self.cancellation_token:
            self.cancellation_token.check_cancelled()
        yield self._head_bytes

        if self.cancellation_token:
            self.cancellation_token.check_cancelled()
        yield self._prompt_bytes

        if self._tech_meta_bytes:
            if self.cancellation_token:
                self.cancellation_token.check_cancelled()
            yield self._tech_meta_bytes

        for path, prefix, suffix in self._source_frames:
            if self.cancellation_token:
                self.cancellation_token.check_cancelled()
            yield prefix

            with open(path, "rb") as f:
                while True:
                    if self.cancellation_token:
                        self.cancellation_token.check_cancelled()
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    yield base64.b64encode(chunk)

            if self.cancellation_token:
                self.cancellation_token.check_cancelled()
            yield suffix

        if self.cancellation_token:
            self.cancellation_token.check_cancelled()
        yield self._tail_bytes


def sanitize_message(msg: str, secrets: Optional[List[Optional[str]]] = None) -> str:
    """Redact secret strings from message to prevent credential leakage."""
    if not secrets:
        return msg
    sanitized = msg
    for s in secrets:
        if s and len(s) >= 4 and s in sanitized:
            sanitized = sanitized.replace(s, "[REDACTED]")
    return sanitized


def extract_json_from_text(text: str) -> Any:
    """Extract and parse JSON from text without repairing editorial content.
    
    Handles plain JSON or fenced ```json ... ``` blocks.
    Raises InvalidGatewayResponseError if text is not valid JSON.
    """
    stripped = text.strip()
    if not stripped:
        raise InvalidGatewayResponseError(
            "Gateway returned an empty response; cannot parse JSON.",
            raw_response=text,
        )

    # Check for markdown code fence
    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped, re.IGNORECASE)
    if fenced_match:
        candidate = fenced_match.group(1).strip()
    else:
        candidate = stripped

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise InvalidGatewayResponseError(
            f"Gateway response failed JSON parsing ({e}). Automatic repair is strictly prohibited.",
            raw_response=text,
        ) from e


@dataclass
class GatewayResult:
    """Container for sanitized Gateway output."""
    raw_response: str
    parsed_json: Optional[Union[Dict[str, Any], List[Any]]] = None
    model: str = ""
    usage: Optional[Dict[str, Any]] = None


class GatewayClient:
    """Client for communicating with the 9router AI Gateway."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:20128",
        api_key: Optional[str] = None,
        timeout: float = 180.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        max_file_size_bytes: Optional[int] = DEFAULT_MAX_FILE_SIZE_BYTES,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.backoff_factor = backoff_factor
        self.max_file_size_bytes = max_file_size_bytes
        self._external_client = client

    def _get_client(self) -> httpx.Client:
        if self._external_client is not None:
            return self._external_client
        return httpx.Client(timeout=self.timeout)

    def _sanitize(self, text: str) -> str:
        return sanitize_message(text, [self.api_key])

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def validate_model_video_capability(
        self,
        model: str,
        cancellation_token: Optional[CancellationToken] = None,
        client: Optional[httpx.Client] = None,
    ) -> bool:
        """Validate that the target model advertises 'videoInput' capability.
        
        Calls GET /v1/models and inspects capabilities.
        Invariants:
        - Combo aliases and models with omitted capabilities are not false rejected.
        - Models explicitly setting videoInput=False are rejected.
        """
        if cancellation_token:
            cancellation_token.check_cancelled()

        url = f"{self.base_url}/v1/models"
        owned = False
        if client is None:
            if self._external_client is not None:
                client = self._external_client
            else:
                client = httpx.Client(timeout=min(10.0, self.timeout))
                owned = True

        try:
            resp = client.get(url, headers=self._headers(), timeout=min(10.0, self.timeout))
            if resp.status_code != 200:
                raise GatewayResponseError(
                    self._sanitize(f"Failed to query models from {url}: HTTP {resp.status_code}")
                )
            data = resp.json()
            models_list = data.get("data", []) if isinstance(data, dict) else []

            for m in models_list:
                if isinstance(m, dict) and m.get("id") == model:
                    if m.get("owned_by") == "combo":
                        return True
                    capabilities = m.get("capabilities")
                    if capabilities is None or not isinstance(capabilities, dict):
                        return True
                    if capabilities.get("videoInput") is False:
                        raise ModelCapabilityError(
                            f"Model '{model}' does not advertise 'videoInput' capability."
                        )
                    return True

            if model in ("sub", "prime"):
                return True

            raise ModelCapabilityError(f"Model '{model}' not found in advertised Gateway models.")
        except (ModelCapabilityError, GatewayResponseError):
            raise
        except Exception as e:
            clean_err = self._sanitize(str(e))
            raise GatewayError(f"Error checking model video capability: {clean_err}") from e
        finally:
            if owned:
                client.close()

    def validate_model_prime_capability(
        self,
        model: str,
        cancellation_token: Optional[CancellationToken] = None,
        client: Optional[httpx.Client] = None,
    ) -> bool:
        """Validate that the target model is available for Prime text chat synthesis.
        
        Calls GET /v1/models and verifies model presence.
        """
        if cancellation_token:
            cancellation_token.check_cancelled()

        if model in ("sub", "prime"):
            return True

        url = f"{self.base_url}/v1/models"
        owned = False
        if client is None:
            if self._external_client is not None:
                client = self._external_client
            else:
                client = httpx.Client(timeout=min(10.0, self.timeout))
                owned = True

        try:
            resp = client.get(url, headers=self._headers(), timeout=min(10.0, self.timeout))
            if resp.status_code != 200:
                raise GatewayResponseError(
                    self._sanitize(f"Failed to query models from {url}: HTTP {resp.status_code}")
                )
            data = resp.json()
            models_list = data.get("data", []) if isinstance(data, dict) else []

            for m in models_list:
                if isinstance(m, dict) and m.get("id") == model:
                    return True

            raise ModelCapabilityError(f"Model '{model}' not found in advertised Gateway models.")
        except (ModelCapabilityError, GatewayResponseError):
            raise
        except Exception as e:
            clean_err = self._sanitize(str(e))
            raise GatewayError(f"Error checking prime model capability: {clean_err}") from e
        finally:
            if owned:
                client.close()

    def _validate_sources(
        self,
        sources: Sequence[Union[Path, str]],
    ) -> List[Tuple[Path, str, int]]:
        """Validate media formats and sizes without reading file contents into memory."""
        if not sources:
            raise ValueError("At least one video source must be provided.")

        validated: List[Tuple[Path, str, int]] = []
        for source in sources:
            path = Path(source).resolve()
            if not path.exists():
                raise FileNotFoundError(f"Source media file does not exist: {path}")

            ext = path.suffix.lower()
            if ext not in SUPPORTED_VIDEO_EXTENSIONS:
                raise UnsupportedMediaError(
                    f"Unsupported media container '{ext}' for file {path.name}. "
                    f"Supported formats: {sorted(list(SUPPORTED_VIDEO_EXTENSIONS.keys()))}. "
                    "Preprocessing or conversion is strictly prohibited."
                )

            size = path.stat().st_size
            if size <= 0:
                raise UnsupportedMediaError(
                    f"Media file '{path.name}' is empty (0 bytes). Zero preprocessing policy forbids repair."
                )
            if self.max_file_size_bytes is not None and size > self.max_file_size_bytes:
                raise UnsupportedMediaError(
                    f"Media file '{path.name}' ({size} bytes) exceeds maximum limit "
                    f"({self.max_file_size_bytes} bytes). Preprocessing or compression is strictly prohibited."
                )

            mime_type = SUPPORTED_VIDEO_EXTENSIONS[ext]
            validated.append((path, mime_type, size))

        return validated

    def _validate_and_encode_sources(
        self,
        sources: Sequence[Union[Path, str]],
    ) -> List[Dict[str, Any]]:
        """Validate media formats/sizes and encode original bytes to data video URIs.
        
        Zero preprocessing: if container or size is invalid, fails immediately.
        """
        validated = self._validate_sources(sources)
        encoded_parts: List[Dict[str, Any]] = []

        for path, mime_type, _ in validated:
            raw_bytes = path.read_bytes()
            b64_data = base64.b64encode(raw_bytes).decode("ascii")
            data_uri = f"data:{mime_type};base64,{b64_data}"

            encoded_parts.append({
                "type": "image_url",
                "image_url": {"url": data_uri},
            })

        return encoded_parts

    def submit_chat_analysis(
        self,
        sources: Sequence[Union[Path, str]],
        prompt: str,
        model: str = "sub",
        technical_schema: Optional[Union[Dict[str, Any], str]] = None,
        source_metadata: Optional[List[Dict[str, Any]]] = None,
        stream: bool = True,
        validate_capability: bool = True,
        cancellation_token: Optional[CancellationToken] = None,
        reasoning_effort: Optional[str] = None,
        expect_json: bool = True,
    ) -> GatewayResult:
        """Submit all ordered sources and prompt in ONE chat request.
        
        Invariants:
        - All ordered sources sent in ONE chat request using verified image_url data video URIs.
        - User prompt is sent exact and unchanged.
        - Technical schema and source metadata are sent separately.
        - Advertised model capability is validated.
        - Explicit supported media/size limits fail without preprocessing.
        - Configured API route (/v1/chat/completions) only.
        - Finite cancel-aware streaming networking with retries only on transient errors.
        - Returns raw sanitized response and parsed JSON without repair.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        if cancellation_token:
            cancellation_token.check_cancelled()

        owned_client = False
        if self._external_client is not None:
            client = self._external_client
        else:
            client = httpx.Client(timeout=self.timeout)
            owned_client = True

        try:
            # Step 1: Validate advertised model capability if enabled
            if validate_capability:
                self.validate_model_video_capability(
                    model, cancellation_token=cancellation_token, client=client
                )

            # Step 2: Validate sources (zero preprocessing, no full file RAM read)
            validated_sources = self._validate_sources(sources)

            # Step 3: Build streaming payload
            payload = StreamingChatPayload(
                sources=validated_sources,
                prompt=prompt,
                model=model,
                stream=stream,
                technical_schema=technical_schema,
                source_metadata=source_metadata,
                cancellation_token=cancellation_token,
                reasoning_effort=reasoning_effort,
            )

            url = f"{self.base_url}/v1/chat/completions"
            headers = self._headers()
            headers["Content-Length"] = str(payload.content_length)

            # Step 4: Execute cancel-aware streaming network request with bounded retries
            last_exception: Optional[Exception] = None

            for attempt in range(self.max_retries + 1):
                if cancellation_token:
                    cancellation_token.check_cancelled()

                try:
                    if stream:
                        raw_text, usage = self._execute_streaming_request(
                            client, url, payload, headers, cancellation_token
                        )
                    else:
                        raw_text, usage = self._execute_sync_request(
                            client, url, payload, headers, cancellation_token
                        )

                    # Step 5: Sanitize response and parse JSON (no repair)
                    sanitized_response = self._sanitize(raw_text)
                    if expect_json:
                        parsed = extract_json_from_text(sanitized_response)
                    else:
                        try:
                            parsed = extract_json_from_text(sanitized_response)
                        except Exception:
                            parsed = None

                    return GatewayResult(
                        raw_response=sanitized_response,
                        parsed_json=parsed,
                        model=model,
                        usage=usage,
                    )

                except CancelledError:
                    raise
                except (ModelCapabilityError, UnsupportedMediaError):
                    # Logical errors: fail immediately without retry
                    raise
                except InvalidGatewayResponseError as e:
                    if not getattr(e, "raw_response", None):
                        e.raw_response = sanitized_response
                    raise
                except GatewayResponseError:
                    # If non-transient status code, fail immediately
                    raise
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                    last_exception = e
                    clean_err = self._sanitize(str(e))
                    if attempt < self.max_retries:
                        sleep_time = self.backoff_factor * (2 ** attempt)
                        if cancellation_token:
                            end_time = time.monotonic() + sleep_time
                            while time.monotonic() < end_time:
                                cancellation_token.check_cancelled()
                                time.sleep(0.05)
                        else:
                            time.sleep(sleep_time)
                        continue
                    else:
                        raise GatewayError(
                            f"Gateway request failed after {self.max_retries + 1} attempts: {clean_err}"
                        ) from e
                except Exception as e:
                    clean_err = self._sanitize(str(e))
                    raise GatewayError(f"Unexpected Gateway error: {clean_err}") from e

            if last_exception:
                raise GatewayError(f"Gateway request failed: {self._sanitize(str(last_exception))}")
            raise GatewayError("Gateway request failed: retries exhausted.")
        finally:
            if owned_client:
                client.close()

    def submit_text_chat(
        self,
        prompt: str,
        model: str = "prime",
        system_prompt: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = True,
        expect_json: bool = True,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> GatewayResult:
        """Submit text-only chat request (Prime stage / synthesis).
        
        Invariants:
        - Text only, no videoInput required.
        - Configured API route (/v1/chat/completions) only.
        - Optional reasoning_effort supported.
        - Cancel-aware streaming networking with transient retries.
        - Returns raw sanitized response and parsed JSON without repair.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        if cancellation_token:
            cancellation_token.check_cancelled()

        owned_client = False
        if self._external_client is not None:
            client = self._external_client
        else:
            client = httpx.Client(timeout=self.timeout)
            owned_client = True

        try:
            messages: List[Dict[str, Any]] = []
            if system_prompt and system_prompt.strip():
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload_dict: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": stream,
            }
            if reasoning_effort and reasoning_effort.strip():
                payload_dict["reasoning_effort"] = reasoning_effort.strip().lower()

            url = f"{self.base_url}/v1/chat/completions"
            headers = self._headers()

            last_exception: Optional[Exception] = None

            for attempt in range(self.max_retries + 1):
                if cancellation_token:
                    cancellation_token.check_cancelled()

                try:
                    if stream:
                        raw_text, usage = self._execute_streaming_request(
                            client, url, payload_dict, headers, cancellation_token
                        )
                    else:
                        raw_text, usage = self._execute_sync_request(
                            client, url, payload_dict, headers, cancellation_token
                        )

                    sanitized_response = self._sanitize(raw_text)
                    if expect_json:
                        parsed = extract_json_from_text(sanitized_response)
                    else:
                        try:
                            parsed = extract_json_from_text(sanitized_response)
                        except Exception:
                            parsed = None

                    return GatewayResult(
                        raw_response=sanitized_response,
                        parsed_json=parsed,
                        model=model,
                        usage=usage,
                    )

                except CancelledError:
                    raise
                except InvalidGatewayResponseError as e:
                    if not getattr(e, "raw_response", None):
                        e.raw_response = sanitized_response
                    raise
                except GatewayResponseError:
                    raise
                except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as e:
                    last_exception = e
                    clean_err = self._sanitize(str(e))
                    if attempt < self.max_retries:
                        sleep_time = self.backoff_factor * (2 ** attempt)
                        if cancellation_token:
                            end_time = time.monotonic() + sleep_time
                            while time.monotonic() < end_time:
                                cancellation_token.check_cancelled()
                                time.sleep(0.05)
                        else:
                            time.sleep(sleep_time)
                        continue
                    else:
                        raise GatewayError(
                            f"Gateway request failed after {self.max_retries + 1} attempts: {clean_err}"
                        ) from e
                except Exception as e:
                    clean_err = self._sanitize(str(e))
                    raise GatewayError(f"Unexpected Gateway error: {clean_err}") from e

            if last_exception:
                raise GatewayError(f"Gateway request failed: {self._sanitize(str(last_exception))}")
            raise GatewayError("Gateway request failed: retries exhausted.")
        finally:
            if owned_client:
                client.close()

    def _execute_streaming_request(
        self,
        client: httpx.Client,
        url: str,
        payload: Union[Dict[str, Any], StreamingChatPayload, Any],
        headers: Dict[str, str],
        cancellation_token: Optional[CancellationToken],
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Execute cancel-aware streaming request handling SSE chunks."""
        collected_chunks: List[str] = []
        usage: Optional[Dict[str, Any]] = None

        req_headers = dict(headers)
        if isinstance(payload, dict):
            kwargs: Dict[str, Any] = {"json": payload}
        else:
            kwargs = {"content": payload}
            if "Content-Type" not in req_headers:
                req_headers["Content-Type"] = "application/json"
            if hasattr(payload, "content_length"):
                req_headers["Content-Length"] = str(payload.content_length)
            elif hasattr(payload, "__len__"):
                req_headers["Content-Length"] = str(len(payload))

        with client.stream("POST", url, headers=req_headers, timeout=self.timeout, **kwargs) as resp:
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", errors="replace")[:300]
                clean_body = self._sanitize(body)
                if resp.status_code in TRANSIENT_STATUS_CODES:
                    raise httpx.HTTPStatusError(
                        f"Transient HTTP {resp.status_code}: {clean_body}",
                        request=resp.request,
                        response=resp,
                    )
                raise GatewayResponseError(
                    f"Gateway returned HTTP {resp.status_code}: {clean_body}"
                )

            for line in resp.iter_lines():
                if cancellation_token and cancellation_token.is_cancelled:
                    resp.close()
                    raise CancelledError("Gateway analysis cancelled during stream.")

                line_str = line.strip()
                if not line_str or line_str.startswith(":"):
                    continue

                if line_str.startswith("data: "):
                    data_str = line_str[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                collected_chunks.append(content)
                        if "usage" in chunk and chunk["usage"]:
                            usage = chunk["usage"]
                    except json.JSONDecodeError:
                        continue

        return "".join(collected_chunks), usage

    def _execute_sync_request(
        self,
        client: httpx.Client,
        url: str,
        payload: Union[Dict[str, Any], StreamingChatPayload, Any],
        headers: Dict[str, str],
        cancellation_token: Optional[CancellationToken],
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Execute synchronous (stream=False) request with cancellation awareness."""
        if cancellation_token:
            cancellation_token.check_cancelled()

        req_headers = dict(headers)
        if isinstance(payload, dict):
            kwargs: Dict[str, Any] = {"json": payload}
        else:
            kwargs = {"content": payload}
            if "Content-Type" not in req_headers:
                req_headers["Content-Type"] = "application/json"
            if hasattr(payload, "content_length"):
                req_headers["Content-Length"] = str(payload.content_length)
            elif hasattr(payload, "__len__"):
                req_headers["Content-Length"] = str(len(payload))

        resp = client.post(url, headers=req_headers, timeout=self.timeout, **kwargs)
        if cancellation_token:
            cancellation_token.check_cancelled()

        if resp.status_code != 200:
            body = resp.text[:300]
            clean_body = self._sanitize(body)
            if resp.status_code in TRANSIENT_STATUS_CODES:
                raise httpx.HTTPStatusError(
                    f"Transient HTTP {resp.status_code}: {clean_body}",
                    request=resp.request,
                    response=resp,
                )
            raise GatewayResponseError(
                f"Gateway returned HTTP {resp.status_code}: {clean_body}"
            )

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise GatewayResponseError("Gateway returned response with no choices.")

        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage")
        return content, usage
