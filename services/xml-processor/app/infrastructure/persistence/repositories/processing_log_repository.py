from typing import List, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.processing_log import ProcessingLog


class ProcessingLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, log: ProcessingLog) -> ProcessingLog:
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def get_all(self, status: Optional[str] = None) -> List[ProcessingLog]:
        query = self.db.query(ProcessingLog)
        if status:
            query = query.filter(ProcessingLog.status == status)
        return query.order_by(ProcessingLog.processed_at.desc()).all()
