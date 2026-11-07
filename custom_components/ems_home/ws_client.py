"""Minimal, dependency-free WebSocket client for the eMS Home local API.

The eMS Home firmware exposes a couple of ``/api/data-transfer/ws/protobuf/...``
streams that push binary protobuf frames.  Home Assistant already ships an
aiohttp based websocket stack, but the firmware is picky about the handshake and
authenticates through a first *text frame* instead of the usual header, so a
small purpose-built client is used here.

Design goals:

* never hang silently – every step has a timeout,
* always reconnect – exponential backoff with jitter,
* answer keep-alive pings, otherwise the device drops the stream after ~60 s,
* reassemble fragmented frames (the device splits larger frames),
* never lose bytes that arrive together with the handshake response,
* expose statistics so a "connected but silent" stream is visible in the UI.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import random
import ssl as _ssl
import struct
import time
from dataclasses import dataclass
from typing import Callable, Optional

_LOGGER = logging.getLogger(__name__)

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

#: How long to wait for the HTTP upgrade response.
HANDSHAKE_TIMEOUT = 10.0
#: While connected, a ping is sent when nothing was received for this long.
PING_INTERVAL = 30.0
#: Close the socket when nothing at all was received for this long.
READ_TIMEOUT = 300.0

#: The wallbox only pushes on change, so minutes without a frame are normal. The
#: link is checked with pings instead; only a long silence is treated as dead.
EVSE_READ_TIMEOUT = 1800.0
#: Maximum backoff between reconnect attempts.
MAX_BACKOFF = 60.0


# ---------------------------------------------------------------------------
# Frame codec
# ---------------------------------------------------------------------------

def encode_frame(opcode: int, payload: bytes, *, fin: bool = True) -> bytes:
    """Encode a client-to-server frame (always masked, as required by RFC 6455)."""
    header = bytearray([(0x80 if fin else 0x00) | opcode])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", length)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", length)

    mask = os.urandom(4)
    header += mask
    masked = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
    return bytes(header) + masked


async def read_frame(
    reader: asyncio.StreamReader, tracker: Optional[dict] = None
) -> tuple[bool, int, bytes]:
    """Read one frame from the socket. Returns ``(fin, opcode, payload)``.

    ``tracker["in_frame"]`` is True while bytes of a frame have already been
    consumed. A timeout then means the stream is desynchronised and has to be
    thrown away – the payload would otherwise be read as the next header.
    """
    first, second = await reader.readexactly(2)
    if tracker is not None:
        # Only now bytes of this frame are gone – a timeout before this point is
        # silence, not a desynchronised frame.
        tracker["in_frame"] = True
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F

    if length == 126:
        length = struct.unpack(">H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", await reader.readexactly(8))[0]

    mask = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(length) if length else b""
    if masked:
        payload = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
    if tracker is not None:
        tracker["in_frame"] = False
    return fin, opcode, payload


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

@dataclass
class StreamStats:
    """Live connection statistics shown in diagnostics and on sensors."""

    name: str
    connected: bool = False
    frames: int = 0
    bytes_received: int = 0
    undecodable_frames: int = 0
    reconnects: int = 0
    last_frame: Optional[float] = None       # monotonic
    connected_since: Optional[float] = None   # monotonic
    last_error: Optional[str] = None
    last_error_at: Optional[float] = None     # wall clock

    def note_frame(self, size: int) -> None:
        self.frames += 1
        self.bytes_received += size
        self.last_frame = time.monotonic()

    def note_error(self, exc: BaseException | str) -> None:
        self.last_error = f"{type(exc).__name__}: {exc}" if isinstance(exc, BaseException) else exc
        self.last_error_at = time.time()

    def reset_connection(self) -> None:
        self.connected = False
        self.connected_since = None

    @property
    def seconds_since_frame(self) -> Optional[float]:
        if self.last_frame is None:
            return None
        return round(time.monotonic() - self.last_frame, 1)

    @property
    def seconds_connected(self) -> Optional[float]:
        if not self.connected or self.connected_since is None:
            return None
        return round(time.monotonic() - self.connected_since, 1)

    def as_dict(self) -> dict:
        return {
            "connected": self.connected,
            "frames_received": self.frames,
            "bytes_received": self.bytes_received,
            "undecodable_frames": self.undecodable_frames,
            "reconnects": self.reconnects,
            "seconds_since_last_frame": self.seconds_since_frame,
            "seconds_connected": self.seconds_connected,
            "last_error": self.last_error,
            "last_error_at": (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.last_error_at))
                if self.last_error_at
                else None
            ),
        }


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class EMSWebSocket:
    """A reconnecting WebSocket stream against one eMS Home.

    ``on_frame`` is called for every complete binary/text message *inside the
    event loop*, so it must be cheap and must not block.
    """

    def __init__(
        self,
        host: str,
        port: int,
        path: str,
        token: str,
        on_frame: Callable[[bytes], None],
        *,
        name: str,
        use_ssl: bool = False,
        on_state_change: Optional[Callable[[bool], None]] = None,
        handshake_timeout: float = HANDSHAKE_TIMEOUT,
        ping_interval: float = PING_INTERVAL,
        read_timeout: float = READ_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._path = path
        self._token = token
        self._on_frame = on_frame
        self._on_state_change = on_state_change
        self._name = name
        self._use_ssl = use_ssl or port == 443
        self._handshake_timeout = handshake_timeout
        self._ping_interval = ping_interval
        self._read_timeout = read_timeout

        self.stats = StreamStats(name=name)
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._writer: Optional[asyncio.StreamWriter] = None

    # -- public API --------------------------------------------------------

    @property
    def path(self) -> str:
        return self._path

    def update_token(self, token: str) -> None:
        """Store a new OAuth token; used on the next (re)connect."""
        if token and token != self._token:
            self._token = token

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name=f"ems_home_ws_{self._name}")

    async def stop(self) -> None:
        self._running = False
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._close_socket()
        if self.stats.connected:
            self.stats.reset_connection()
            self._notify_state(False)

    # -- internals ---------------------------------------------------------

    def _notify_state(self, connected: bool) -> None:
        if self._on_state_change is not None:
            try:
                self._on_state_change(connected)
            except Exception:  # pragma: no cover - defensive
                _LOGGER.exception("%s: state callback failed", self._name)

    def _next_backoff(self, attempt: int) -> float:
        base = min(MAX_BACKOFF, 2 ** min(attempt, 6))
        return base * (0.75 + random.random() * 0.5)

    async def _run(self) -> None:
        attempt = 0
        while self._running:
            try:
                await self._session()
                # Clean close by the server -> reconnect quickly
                attempt = 0
                self._announced = False
                self._recovered = False
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001 - keep the stream alive
                self.stats.note_error(exc)
                if getattr(self, "_recovered", False):
                    # The link worked before this failure, so this starts a new
                    # series: wait a second and allow a warning again.
                    self._recovered = False
                    attempt = 0
                    self._announced = False
                delay = self._next_backoff(attempt)
                attempt += 1
                self.stats.reconnects += 1
                # A device that refuses connections for a while must not flood the
                # log: the first failure is worth a warning, the rest is noise.
                if getattr(self, "_announced", False):
                    _LOGGER.debug(
                        "%s: still failing (%s) – reconnecting in %.0f s",
                        self._name, exc, delay,
                    )
                else:
                    self._announced = True
                    _LOGGER.warning(
                        "%s: %s – reconnecting in %.0f s", self._name, exc, delay
                    )
                await asyncio.sleep(delay)
            finally:
                await self._close_socket()
                if self.stats.connected:
                    self.stats.reset_connection()
                    self._notify_state(False)

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        ssl_ctx = None
        if self._use_ssl:
            ssl_ctx = _ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = _ssl.CERT_NONE

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port, ssl=ssl_ctx),
            self._handshake_timeout,
        )
        self._writer = writer

        key = base64.b64encode(os.urandom(16)).decode()
        host_header = self._host
        if self._port not in (80, 443):
            host_header = f"{self._host}:{self._port}"

        request = (
            f"GET {self._path} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"Authorization: Bearer {self._token}\r\n"
            f"Origin: {'https' if self._use_ssl else 'http'}://{host_header}\r\n"
            "User-Agent: HomeAssistant (ems_home)\r\n"
            "\r\n"
        )
        writer.write(request.encode())
        await writer.drain()

        # ``readuntil`` leaves any bytes that arrived after the header block in
        # the stream buffer.  The previous implementation threw them away, which
        # could lose the first frames of a burst.
        try:
            head = await asyncio.wait_for(
                reader.readuntil(b"\r\n\r\n"), self._handshake_timeout
            )
        except asyncio.TimeoutError as exc:
            raise ConnectionError(
                f"handshake timed out after {self._handshake_timeout:.0f}s"
            ) from exc

        status_line = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        if " 101" not in status_line:
            raise ConnectionError(f"upgrade rejected: {status_line}")
        return reader, writer

    async def _session(self) -> None:
        reader, writer = await self._open()

        # The firmware authenticates the stream with a first text frame; the
        # Authorization header alone is not enough.
        writer.write(encode_frame(OP_TEXT, f"Bearer {self._token}".encode()))
        await writer.drain()

        self.stats.connected = True
        self.stats.connected_since = time.monotonic()
        self._notify_state(True)
        _LOGGER.info("%s: connected", self._name)
        # A working connection ends the failure series – even if the server later
        # closes it with an error. Otherwise the backoff keeps growing and later
        # outages are only logged at debug level.
        self._recovered = True

        buffer = bytearray()
        buffer_opcode: Optional[int] = None
        frame_tracker: dict = {"in_frame": False}
        last_rx = time.monotonic()

        while self._running:
            try:
                # The timeout doubles as the keep-alive tick: the firmware sends
                # sparse frames (the wallbox only pushes on change), so waiting
                # for a frame without a timeout would never detect a dead link.
                fin, opcode, payload = await asyncio.wait_for(
                    read_frame(reader, frame_tracker), self._ping_interval
                )
            except asyncio.TimeoutError:
                # If bytes of a frame are already buffered, the timeout hit in the
                # middle of a frame: continuing would read the payload as the next
                # header and desync the stream for good. Reconnect instead.
                if frame_tracker.get("in_frame") or getattr(reader, "_buffer", b""):
                    raise ConnectionError("frame read timed out mid-frame – resyncing") from None
                if time.monotonic() - last_rx > self._read_timeout:
                    raise ConnectionError(
                        f"no data for {self._read_timeout:.0f}s"
                    )
                writer.write(encode_frame(OP_PING, b""))
                await writer.drain()
                continue

            last_rx = time.monotonic()

            if opcode == OP_CLOSE:
                raise ConnectionError("server closed the stream")
            if opcode == OP_PING:
                writer.write(encode_frame(OP_PONG, payload))
                await writer.drain()
                continue
            if opcode == OP_PONG:
                continue

            if opcode == OP_CONT:
                buffer += payload
                if fin:
                    opcode = buffer_opcode or OP_BINARY
                    payload = bytes(buffer)
                    buffer.clear()
                    buffer_opcode = None
                else:
                    continue
            elif not fin:
                buffer = bytearray(payload)
                buffer_opcode = opcode
                continue
            else:
                payload = payload

            self.stats.note_frame(len(payload))
            _LOGGER.debug("%s: frame #%d (%d bytes)", self._name, self.stats.frames, len(payload))
            try:
                self._on_frame(payload)
            except Exception:  # pragma: no cover - never kill the stream
                _LOGGER.exception("%s: frame handler failed", self._name)

    async def _close_socket(self) -> None:
        writer, self._writer = self._writer, None
        if writer is None:
            return
        with contextlib.suppress(Exception):
            writer.write(encode_frame(OP_CLOSE, b""))
            await asyncio.wait_for(writer.drain(), 2)
        with contextlib.suppress(Exception):
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), 2)
