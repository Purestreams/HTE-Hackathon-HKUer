import sys
import time
from dataclasses import dataclass
from typing import Iterable, Optional


def estimate_tokens(text: str) -> int:
    """Heuristic token estimator.

    Works reasonably for mixed EN/ZH:
    - counts CJK chars as ~1 token
    - counts non-CJK chars as ~1 token per 4 chars
    """
    if not text:
        return 0

    cjk = 0
    other = 0
    for ch in text:
        o = ord(ch)
        # Basic CJK Unified Ideographs + extensions (rough)
        if (
            0x4E00 <= o <= 0x9FFF
            or 0x3400 <= o <= 0x4DBF
            or 0x20000 <= o <= 0x2A6DF
            or 0x2A700 <= o <= 0x2B73F
            or 0x2B740 <= o <= 0x2B81F
            or 0x2B820 <= o <= 0x2CEAF
        ):
            cjk += 1
        else:
            other += 1

    return cjk + max(1, other // 4)


@dataclass
class TokenRateProgress:
    label: str = "stream"
    update_every_s: float = 1.0
    target_tps: float = 200.0

    _start: float = 0.0
    _last_update: float = 0.0
    _last_tok: int = 0

    def start(self) -> None:
        now = time.monotonic()
        self._start = now
        self._last_update = now
        self._last_tok = 0
        self._render(0, 0.0, 0.0)

    def update(self, total_tokens: int) -> None:
        now = time.monotonic()
        dt = now - self._last_update
        if dt < self.update_every_s:
            return
        delta = total_tokens - self._last_tok
        tps = (delta / dt) if dt > 0 else 0.0
        elapsed = now - self._start
        self._last_update = now
        self._last_tok = total_tokens
        self._render(total_tokens, tps, elapsed)

    def finish(self, total_tokens: int) -> None:
        elapsed = max(1e-6, time.monotonic() - self._start)
        avg = total_tokens / elapsed
        self._render(total_tokens, avg, elapsed)
        sys.stderr.write("\n")
        sys.stderr.flush()

    def _render(self, total_tokens: int, tps: float, elapsed: float) -> None:
        bar_len = 24
        fill = 0
        if self.target_tps > 0:
            fill = int(min(bar_len, round(bar_len * (tps / self.target_tps))))
        bar = "#" * fill + "." * (bar_len - fill)
        msg = f"[{bar}] {self.label} | {elapsed:5.1f}s | ~{tps:6.1f} tok/s | ~{total_tokens} tok"
        sys.stderr.write("\r" + msg[:120].ljust(120))
        sys.stderr.flush()


def stream_text_from_ark_response(stream: Iterable[object]) -> str:
    """Best-effort extractor for Ark stream chunks.

    Supports different chunk schemas by introspection.
    """
    parts: list[str] = []
    for chunk in stream:
        # Try common OpenAI-like chunk shape: chunk.choices[0].delta.content
        try:
            choices = getattr(chunk, "choices", None)
            if choices:
                choice0 = choices[0]
                delta = getattr(choice0, "delta", None)
                if delta is not None:
                    content = getattr(delta, "content", None)
                    if content:
                        parts.append(str(content))
                        continue
                # Some SDKs stream message directly
                message = getattr(choice0, "message", None)
                if message is not None:
                    content2 = getattr(message, "content", None)
                    if content2:
                        parts.append(str(content2))
                        continue
        except Exception:
            pass

        # Fallback: string chunk
        try:
            if isinstance(chunk, str):
                parts.append(chunk)
        except Exception:
            pass

    return "".join(parts)
