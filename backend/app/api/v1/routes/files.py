from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_db, require_permission
from app.schemas.files import IngestRequest, IngestResult, UploadedFileOut
from app.services.file_service import FileService

router = APIRouter(
    prefix="/api/files",
    tags=["files"],
)


@router.post("/upload", response_model=UploadedFileOut, status_code=201, dependencies=[Depends(require_permission("files:manage"))])
async def upload_file(
    file: UploadFile = File(...),
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await FileService(db).save_upload(org_id, file)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("", response_model=list[UploadedFileOut], dependencies=[Depends(require_permission("files:read"))])
async def list_files(org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    return await FileService(db).list(org_id)


@router.delete("/{id}", dependencies=[Depends(require_permission("files:manage"))])
async def delete_file(
    id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)
):
    if not await FileService(db).delete(org_id, id):
        raise HTTPException(404, "file not found")
    return {"ok": True}


@router.post("/{id}/ingest", response_model=IngestResult, dependencies=[Depends(require_permission("files:manage"))])
async def ingest_file(
    id: str,
    body: IngestRequest,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await FileService(db).ingest_to_rag(
            org_id, id, body.collection, body.chunk_size, body.chunk_overlap, body.tags
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
