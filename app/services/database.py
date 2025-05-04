from sqlalchemy.orm import Session
from app.models.base import File, Document
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseService:
    def __init__(self, db: Session):
        self.db = db

    def create_file_record(self, filename: str, file_type: str) -> File:
        """
        Crea un registro de archivo en la base de datos
        """
        file = File(
            filename=filename,
            file_type=file_type,
            status='pending'
        )
        self.db.add(file)
        self.db.commit()
        self.db.refresh(file)
        return file

    def create_document_record(self, file_id: int, document_name: str) -> Document:
        """
        Crea un registro de documento en la base de datos
        """
        document = Document(
            file_id=file_id,
            document_name=document_name,
            status='pending'
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def update_file_status(self, file_id: int, status: str, error_message: str = None):
        """
        Actualiza el estado de un archivo
        """
        file = self.db.query(File).filter(File.id == file_id).first()
        if file:
            file.status = status
            if error_message:
                file.error_message = error_message
            self.db.commit()

    def update_document_status(self, document_id: int, status: str, error_message: str = None):
        """
        Actualiza el estado de un documento
        """
        document = self.db.query(Document).filter(Document.id == document_id).first()
        if document:
            document.status = status
            if error_message:
                document.error_message = error_message
            self.db.commit()

    def get_processing_files(self) -> list[File]:
        """
        Obtiene los archivos que están en proceso
        """
        return self.db.query(File).filter(File.status.in_(['pending', 'processing'])).all()

    def get_file_by_id(self, file_id: int) -> File:
        """
        Obtiene un archivo por su ID
        """
        return self.db.query(File).filter(File.id == file_id).first()
