from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import pytest
from starlette.datastructures import UploadFile

from app.services.file_service import FileService


@pytest.mark.asyncio
async def test_file_service_allows_image_extensions() -> None:
    fake_db = AsyncMock()
    service = FileService(fake_db)

    service.repo.create = AsyncMock(side_effect=lambda record: record)

    image_extensions = [".png", ".jpg", ".jpeg", ".gif", ".webp"]

    with patch.object(service, "_s3_client"), patch.object(service, "_ensure_bucket"):
        for ext in image_extensions:
            filename = f"test_image{ext}"
            upload_file = UploadFile(
                filename=filename,
                file=io.BytesIO(b"fake image data"),
                size=15,
                headers={"content-type": f"image/{ext.lstrip('.')}"},
            )
            record = await service.save_upload(
                org_id="org-test",
                file=upload_file,
                user_id="user-test",
            )
            assert record.original_name == filename
            assert record.stored_path.endswith(ext)


@pytest.mark.asyncio
async def test_file_service_rejects_unsupported_extensions() -> None:
    fake_db = AsyncMock()
    service = FileService(fake_db)

    upload_file = UploadFile(
        filename="malicious.exe",
        file=io.BytesIO(b"executable content"),
        size=18,
    )
    with pytest.raises(ValueError, match="Unsupported file type: .exe"):
        await service.save_upload(
            org_id="org-test",
            file=upload_file,
            user_id="user-test",
        )
