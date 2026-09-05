from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_loop import format_multimodal_user_content
from app.core.session_surface import derive_messages
from app.models.session_event import SessionEvent
from app.services.chat_service import ChatService


def test_format_multimodal_user_content_openai() -> None:
    images = [{"mime_type": "image/png", "data_b64": "iVBORw0KGgo=", "name": "test.png"}]
    blocks = format_multimodal_user_content("Describe this diagram", images, "openai_compatible")
    assert blocks == [
        {"type": "text", "text": "Describe this diagram"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}},
    ]


def test_format_multimodal_user_content_anthropic() -> None:
    images = [{"mime_type": "image/jpeg", "data_b64": "/9j/4AAQSkZJRg==", "name": "photo.jpg"}]
    blocks = format_multimodal_user_content("Analyze this photo", images, "anthropic")
    assert blocks == [
        {"type": "text", "text": "Analyze this photo"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": "/9j/4AAQSkZJRg==",
            },
        },
    ]


def test_format_multimodal_user_content_gemini() -> None:
    images = [{"mime_type": "image/webp", "data_b64": "UklGR==", "name": "graphic.webp"}]
    blocks = format_multimodal_user_content("Read the chart", images, "gemini")
    assert blocks == [
        {"text": "Read the chart"},
        {
            "inline_data": {
                "mime_type": "image/webp",
                "data": "UklGR==",
            }
        },
    ]


@pytest.mark.asyncio
async def test_inline_attachments_vision_supported() -> None:
    fake_db = AsyncMock()
    service = ChatService(fake_db)

    file_record = MagicMock()
    file_record.original_name = "diagram.png"
    file_record.size = len(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")
    file_record.content_type = "image/png"
    fake_png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."

    with patch(
        "app.services.file_service.FileService.download",
        return_value=(fake_png_data, file_record),
    ):
        prompt, meta, images, warnings = await service._inline_attachments(
            org_id="org-1",
            message="Please examine the attached system architecture.",
            attachment_ids=["file-123"],
            user_id="user-1",
            supports_vision=True,
        )

        assert prompt == "Please examine the attached system architecture."
        assert meta == [
            {
                "id": "file-123",
                "name": "diagram.png",
                "size": file_record.size,
                "content_type": "image/png",
            }
        ]
        assert len(images) == 1
        assert images[0]["mime_type"] == "image/png"
        assert images[0]["data_b64"] == base64.b64encode(fake_png_data).decode("utf-8")
        assert warnings == []


@pytest.mark.asyncio
async def test_inline_attachments_vision_oversized_image() -> None:
    fake_db = AsyncMock()
    service = ChatService(fake_db)

    file_record = MagicMock()
    file_record.original_name = "huge_photo.jpg"
    huge_data = b"0" * (6 * 1024 * 1024)  # 6MB

    with patch(
        "app.services.file_service.FileService.download",
        return_value=(huge_data, file_record),
    ):
        prompt, meta, images, warnings = await service._inline_attachments(
            org_id="org-1",
            message="Check this picture.",
            attachment_ids=["file-huge"],
            user_id="user-1",
            supports_vision=True,
        )

        assert len(images) == 0
        assert len(warnings) == 1
        assert "image size exceeds 5MB limit" in warnings[0]
        assert "could not read 'huge_photo.jpg'" in prompt
        assert meta[0]["error"] is not None


@pytest.mark.asyncio
async def test_inline_attachments_vision_unsupported_notifies_and_warns() -> None:
    fake_db = AsyncMock()
    service = ChatService(fake_db)

    file_record = MagicMock()
    file_record.original_name = "screenshot.png"
    file_record.size = len(b"\x89PNG...")
    file_record.content_type = "image/png"
    fake_png_data = b"\x89PNG..."

    with (
        patch(
            "app.services.file_service.FileService.download",
            return_value=(fake_png_data, file_record),
        ),
        patch("app.services.chat_service.extract_text") as mock_extract,
    ):
        prompt, meta, images, warnings = await service._inline_attachments(
            org_id="org-1",
            message="Read this text screenshot.",
            attachment_ids=["file-img"],
            user_id="user-1",
            supports_vision=False,
        )

        # Non-vision model should NEVER call extract_text or docling for images
        mock_extract.assert_not_called()
        assert len(images) == 0
        assert "Current model does not support visual image inputs (Vision)" in prompt
        assert meta == [
            {
                "id": "file-img",
                "name": "screenshot.png",
                "size": file_record.size,
                "content_type": "image/png",
                "error": "Model does not support vision",
            }
        ]
        assert len(warnings) == 1
        assert "không hỗ trợ đọc ảnh (Vision)" in warnings[0]



def test_derive_messages_preserves_multimodal_list_content() -> None:
    multimodal_blocks = [
        {"type": "text", "text": "What is in this image?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,ABC"}},
    ]
    ev = SessionEvent(
        id="ev-1",
        session_id="s-1",
        org_id="org-1",
        seq=1,
        type="user/message",
        data={"content": multimodal_blocks},
    )

    messages = derive_messages([ev])
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == multimodal_blocks
    assert isinstance(messages[0]["content"], list)
