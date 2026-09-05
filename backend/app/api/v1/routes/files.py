from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz.policy import PrincipalContext
from app.dependencies import (
    get_current_org_id,
    get_current_user,
    get_db,
    require_any_permission,
    require_permission,
)
from app.models.user import User
from app.schemas.files import IngestJobOut, IngestJobRecord, IngestRequest, UploadedFileOut
from app.services.file_ingestion_service import FileIngestionService
from app.services.file_service import FileService
from app.services.quota_service import QuotaService

router = APIRouter(
    prefix="/api/files",
    tags=["files"],
)


@router.post("/upload", response_model=UploadedFileOut, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    authz: PrincipalContext = Depends(require_permission("files:write")),
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
        # Plain ``user`` members are self-scoped (owner_user_id is set only
        # for that role): their uploads stay personal, staff uploads are
        # organization-visible.
        visibility = "personal" if authz.owner_user_id else "organization"
        return await FileService(db).save_upload(org_id, file, current_user.id, visibility)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("", response_model=list[UploadedFileOut])
async def list_files(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    authz: PrincipalContext = Depends(require_permission("files:read")),
    db: AsyncSession = Depends(get_db),
):
    owner = authz.owner_user_id
    files = await FileService(db).list(org_id, owner_user_id=owner)

    # Join User to get creator email/name (avoid N+1)
    user_ids = [f.created_by_user_id for f in files if f.created_by_user_id]
    user_map: dict[str, User] = {}
    if user_ids:
        res = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in res.scalars().all():
            user_map[u.id] = u

    return [
        UploadedFileOut(
            id=f.id,
            original_name=f.original_name,
            content_type=f.content_type,
            size=f.size,
            status=f.status,
            visibility=f.visibility,
            collection=f.collection,
            error=f.error,
            created_by_user_id=f.created_by_user_id,
            creator_email=user_map[f.created_by_user_id].email if f.created_by_user_id and f.created_by_user_id in user_map else None,
            creator_name=user_map[f.created_by_user_id].display_name if f.created_by_user_id and f.created_by_user_id in user_map else None,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in files
    ]


@router.delete("/{id}")
async def delete_file(
    id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    authz: PrincipalContext = Depends(require_permission("files:write")),
    db: AsyncSession = Depends(get_db),
):
    owner = authz.owner_user_id
    if not await FileService(db).delete(org_id, id, owner_user_id=owner):
        raise HTTPException(404, "file not found")
    return {"ok": True}


@router.get("/{id}/content")
async def get_file_content(
    id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    authz: PrincipalContext = Depends(require_permission("files:read")),
    db: AsyncSession = Depends(get_db),
):
    import mimetypes

    owner = authz.owner_user_id
    result = await FileService(db).download(org_id, id, owner_user_id=owner)
    if result is None:
        raise HTTPException(404, "file not found")
    data, record = result

    content_type, _ = mimetypes.guess_type(record.original_name)
    if not content_type:
        content_type = "application/octet-stream"

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{record.original_name}"',
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.post("/{id}/ingest", response_model=IngestJobOut, status_code=202)
async def ingest_file(
    id: str,
    body: IngestRequest,
    response: Response,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    authz: PrincipalContext = Depends(require_any_permission("files:manage", "files:personal:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        import uuid

        # Staff (files:manage) may ingest any file in the org; a plain user
        # with only files:personal:manage is scoped to files they own —
        # same convention as list/download/delete in this router.
        owner_user_id = None if authz.allows("files:manage") else authz.owner_user_id
        job, deduplicated = await FileIngestionService(db).create_job(
            org_id, id, current_user.id, collection=body.collection,
            chunk_size=body.chunk_size, chunk_overlap=body.chunk_overlap,
            tags=body.tags, correlation_id=str(uuid.uuid4()),
            owner_user_id=owner_user_id,
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
