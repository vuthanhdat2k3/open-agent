from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.files import IngestJobOut, IngestJobRecord, IngestRequest, UploadedFileOut
from app.services.file_ingestion_service import FileIngestionService
from app.services.file_service import FileService
from app.services.quota_service import QuotaService

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
    quota = await QuotaService(db).get_for_update(org_id)
    if (
        quota is not None
        and quota.max_storage_bytes is not None
        and await QuotaService(db).storage_bytes(org_id)
        + int(file.size or 0)
        > quota.max_storage_bytes
        and quota.enforcement_mode == "enforce"
    ):
        raise HTTPException(429, "storage quota reached")
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


@router.post("/{id}/ingest", response_model=IngestJobOut, status_code=202, dependencies=[Depends(require_permission("files:manage"))])
async def ingest_file(
    id: str,
    body: IngestRequest,
    response: Response,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        import uuid

        job, deduplicated = await FileIngestionService(db).create_job(
            org_id, id, current_user.id, collection=body.collection,
            chunk_size=body.chunk_size, chunk_overlap=body.chunk_overlap,
            tags=body.tags, correlation_id=str(uuid.uuid4()),
        )
        if deduplicated and job.status == "succeeded":
            response.status_code = 200
        return IngestJobOut(
            job_id=job.id, file_id=job.file_id, status=job.status,
            deduplicated=deduplicated, attempt_count=job.attempt_count,
            max_attempts=job.max_attempts, rag_document_id=job.rag_document_id,
            chunk_count=job.chunk_count, warnings=job.warnings or [],
            error_code=job.error_code, error_detail=job.error_detail,
            created_at=job.created_at, updated_at=job.updated_at,
        )
    except FileNotFoundError:
        raise HTTPException(404, "file not found")
    except FileExistsError as e:
        raise HTTPException(409, str(e))


@router.get("/{id}/ingest-jobs", response_model=list[IngestJobRecord], dependencies=[Depends(require_permission("files:read"))])
async def list_ingest_jobs(id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    from app.models.file_ingest_job import FileIngestJob

    jobs = list((await db.scalars(select(FileIngestJob).where(
        FileIngestJob.file_id == id, FileIngestJob.org_id == org_id
    ).order_by(FileIngestJob.created_at.desc()))).all())
    return jobs


@router.get("/{id}/ingest-jobs/{job_id}", response_model=IngestJobRecord, dependencies=[Depends(require_permission("files:read"))])
async def get_ingest_job(id: str, job_id: str, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    from app.models.file_ingest_job import FileIngestJob

    job = await db.scalar(select(FileIngestJob).where(
        FileIngestJob.id == job_id, FileIngestJob.file_id == id, FileIngestJob.org_id == org_id
    ))
    if job is None:
        raise HTTPException(404, "ingest job not found")
    return job
