"""数字人流式语音分段与请求内合成。"""

import asyncio
import base64
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from uuid import uuid4

from app.modules.digital_human.constants import DIGITAL_HUMAN_TTS_REQUEST_TIMEOUT_SECONDS
from app.modules.digital_human.service.service import DigitalHumanService
from app.shared.streaming import EventType, StreamEvent

logger = logging.getLogger(__name__)
FIRST_MIN = 12
LATER_MIN = 20
TARGET = 40
MAX_LENGTH = 100
QUEUE_CAPACITY = 8
MAX_SEGMENT_AUDIO_BYTES = 2 * 1024 * 1024
STRONG = "。！？!?；;"
WEAK = "，,：:"


def speech_text(text: str) -> str:
    """清理 Markdown 朗读标记；输入原始片段，输出语音文本；调用方：分段器。"""
    text = re.sub(r"```[^\n]*\n?[\s\S]*?```", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}|[-*+]|\d+[.)])\s+", "", text)
    return re.sub(r"[*_~`]", "", text).strip()


class SpeechSegmenter:
    """增量缓存未完成语句，在自然停顿处提交给数字人 TTS。"""

    def __init__(self) -> None:
        self.buffer = ""
        self.first = True

    def feed(self, text: str, *, final: bool = False) -> list[str]:
        """追加模型增量并输出完整语音段；final 时清空剩余内容；调用方：语音流水线。"""
        self.buffer += text
        segments: list[str] = []
        while self.buffer:
            cut = self._cut(final)
            if not cut:
                break
            raw, self.buffer = self.buffer[:cut], self.buffer[cut:]
            cleaned = speech_text(raw)
            if cleaned:
                segments.append(cleaned)
                self.first = False
        return segments

    def _cut(self, final: bool) -> int:
        # 未闭合的代码、链接和 URL 保持完整，避免在增量边界误切。
        in_code = False
        link_depth = 0
        index = 0
        minimum = FIRST_MIN if self.first else LATER_MIN
        weak = 0
        while index < len(self.buffer):
            if self.buffer.startswith("```", index):
                in_code = not in_code
                index += 3
                continue
            char = self.buffer[index]
            if not in_code:
                if char == "[":
                    link_depth += 1
                elif char == "]" and link_depth:
                    link_depth -= 1
                    if index + 1 >= len(self.buffer) and not final:
                        break
                elif char == "(" and index and self.buffer[index - 1] == "]":
                    link_depth += 1
                elif char == ")" and link_depth:
                    link_depth -= 1
                token_start = (
                    max(self.buffer.rfind(" ", 0, index), self.buffer.rfind("\n", 0, index)) + 1
                )
                token = self.buffer[token_start : index + 1]
                in_url = "//" in token or token.startswith(("http", "www."))
                if not link_depth and not in_url:
                    length = index + 1
                    if char in STRONG and length >= minimum:
                        while length < len(self.buffer) and self.buffer[length] in STRONG:
                            length += 1
                        if length == len(self.buffer) and not final:
                            break
                        return length
                    if (
                        char == "."
                        and length >= minimum
                        and index + 1 < len(self.buffer)
                        and self.buffer[index + 1].isspace()
                    ):
                        return length
                    if char in WEAK and length >= minimum:
                        weak = length
                        if self.first or length >= TARGET:
                            return length
                    if length >= MAX_LENGTH:
                        if weak:
                            return weak
                        # 优先词边界；超长单词没有自然边界时按上限兜底。
                        if char.isascii() and char.isalnum() and token_start >= minimum:
                            return token_start
                        return length
            index += 1
        return len(self.buffer) if final else 0


async def stream_speech(
    messages: AsyncIterator[StreamEvent], service: DigitalHumanService
) -> AsyncIterator[StreamEvent]:
    """并行转发会话事件与顺序合成语音；关闭迭代器时取消全部请求内任务。"""
    turn_id = uuid4().hex
    started = time.monotonic()
    text_queue: asyncio.Queue[str | None] = asyncio.Queue(QUEUE_CAPACITY)
    events: asyncio.Queue[StreamEvent | None] = asyncio.Queue(QUEUE_CAPACITY)
    segmenter = SpeechSegmenter()
    first_token = True
    first_segment = True

    def metric(name: str) -> None:
        logger.info(
            "digital_human_%s turn_id=%s elapsed_ms=%.0f",
            name,
            turn_id,
            (time.monotonic() - started) * 1000,
        )

    async def produce() -> None:
        nonlocal first_token, first_segment
        try:
            async for event in messages:
                await events.put(event)
                if event.data.get("type") == "text_delta":
                    if first_token:
                        metric("llm_first_token")
                        first_token = False
                    for segment in segmenter.feed(str(event.data["content"])):
                        if first_segment:
                            metric("first_segment_ready")
                            first_segment = False
                        await text_queue.put(segment)
            for segment in segmenter.feed("", final=True):
                if first_segment:
                    metric("first_segment_ready")
                    first_segment = False
                await text_queue.put(segment)
            metric("llm_complete")
        except asyncio.CancelledError:
            raise
        else:
            await text_queue.put(None)

    async def consume() -> None:
        segment_id = 0
        failed = False
        while (segment := await text_queue.get()) is not None:
            if failed:
                continue
            try:
                metric("tts_request_start")
                async with asyncio.timeout(DIGITAL_HUMAN_TTS_REQUEST_TIMEOUT_SECONDS * 2):
                    audio = await service.synthesize(segment)
                if len(audio) > MAX_SEGMENT_AUDIO_BYTES:
                    raise ValueError("语音片段超过传输大小限制")
                segment_id += 1
                if segment_id == 1:
                    metric("tts_first_segment_ready")
                await events.put(
                    StreamEvent(
                        event_type=EventType.MESSAGE,
                        data={
                            "type": "audio_segment",
                            "turn_id": turn_id,
                            "segment_id": segment_id,
                            "format": "mp3",
                            "audio": base64.b64encode(audio).decode("ascii"),
                        },
                    )
                )
            except Exception as error:
                logger.warning(
                    "digital_human_audio_failed turn_id=%s error_type=%s",
                    turn_id,
                    type(error).__name__,
                )
                failed = True
                await events.put(
                    StreamEvent(
                        event_type=EventType.MESSAGE,
                        data={"type": "audio_error", "turn_id": turn_id},
                    )
                )
        metric("audio_complete")
        await events.put(
            StreamEvent(
                event_type=EventType.MESSAGE, data={"type": "audio_done", "turn_id": turn_id}
            )
        )

    async def run() -> None:
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(produce())
                group.create_task(consume())
        finally:
            if not asyncio.current_task().cancelling():
                await events.put(None)

    metric("request_start")
    task = asyncio.create_task(run())
    try:
        while (event := await events.get()) is not None:
            yield event
        await task
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await messages.aclose()
