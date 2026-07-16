from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_api_key
from app.db.session import get_db
from app.schemas.files import IngestRequest, IngestResult, UploadedFileOut
from app.services.file_service import FileService

router = APIRouter(
    prefix="/api/files",
    tags=["files"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/upload", response_model=UploadedFileOut, status_code=201)
async def upload_file(
    file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    try:
        return await FileService(db).save_upload(file)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("", response_model=list[UploadedFileOut])
async def list_files(db: AsyncSession = Depends(get_db)):
    return await FileService(db).list()


@router.delete("/{id}")
async def delete_file(id: str, db: AsyncSession = Depends(get_db)):
    if not await FileService(db).delete(id):
        raise HTTPException(404, "file not found")
    return {"ok": True}


@router.post("/{id}/ingest", response_model=IngestResult)
async def ingest_file(
    id: str, body: IngestRequest, db: AsyncSession = Depends(get_db)
):
    try:
        return await FileService(db).ingest_to_rag(
            id, body.collection, body.chunk_size, body.chunk_overlap, body.tags
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
