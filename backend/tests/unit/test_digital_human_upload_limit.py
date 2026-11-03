from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.modules.digital_human.middleware.upload_limit import (
    MULTIPART_OVERHEAD_BYTES,
    UPLOAD_PATH_SUFFIX,
    DigitalHumanAudioUploadLimitMiddleware,
)


def test_upload_limit_rejects_oversized_request_before_route_parsing() -> None:
    application = FastAPI()
    application.add_middleware(DigitalHumanAudioUploadLimitMiddleware, max_audio_bytes=1)
    route_called = False

    @application.post(UPLOAD_PATH_SUFFIX)
    async def receive_audio(request: Request) -> dict[str, int]:
        nonlocal route_called
        route_called = True
        return {"size": len(await request.body())}

    with TestClient(application) as client:
        response = client.post(
            UPLOAD_PATH_SUFFIX,
            content=b"x" * (MULTIPART_OVERHEAD_BYTES + 2),
            headers={"Content-Type": "multipart/form-data; boundary=test"},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "录音文件超过大小限制。"}
    assert route_called is False
