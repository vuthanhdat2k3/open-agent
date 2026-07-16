from app.models.files import UploadedFile
from app.repositories.base import BaseRepository


class UploadedFileRepository(BaseRepository[UploadedFile]):
    def __init__(self, db):
        super().__init__(UploadedFile, db)
