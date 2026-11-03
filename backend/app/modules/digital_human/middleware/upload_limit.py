"""在 multipart 解析前限制数字人录音请求体大小。"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

UPLOAD_PATH_SUFFIX = "/digital-human/speech/recognitions"
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class _RequestBodyTooLarge(Exception):
    """请求体超过路由配置的最大字节数。"""


class DigitalHumanAudioUploadLimitMiddleware:
    """限制录音路由的请求体，避免 Starlette 先解析超大 multipart 文件。"""

    def __init__(self, app: ASGIApp, *, max_audio_bytes: int) -> None:
        self._app = app
        self._max_request_bytes = max_audio_bytes + MULTIPART_OVERHEAD_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").endswith(UPLOAD_PATH_SUFFIX):
            await self._app(scope, receive, send)
            return

        content_length = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"content-length"),
            None,
        )
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = 0
            if declared_size > self._max_request_bytes:
                await self._send_too_large(send)
                return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self._max_request_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if not response_started:
                await self._send_too_large(send)

    @staticmethod
    async def _send_too_large(send: Send) -> None:
        body = '{"detail":"录音文件超过大小限制。"}'.encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
