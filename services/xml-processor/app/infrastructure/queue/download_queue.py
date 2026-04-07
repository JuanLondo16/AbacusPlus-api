import asyncio
import logging
import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional

import httpx

from app.domain.exceptions.base import DuplicateEntityException
from app.infrastructure.clients.rag_client import RagClient
from app.infrastructure.config.database import SessionLocal
from app.infrastructure.persistence.models.processing_log import ProcessingLog
from app.infrastructure.persistence.repositories.concept_repository import ConceptRepository
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository
from app.infrastructure.persistence.repositories.issuer_repository import IssuerRepository
from app.infrastructure.persistence.repositories.processing_log_repository import ProcessingLogRepository
from app.infrastructure.persistence.repositories.receiver_repository import ReceiverRepository
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository
from app.application.use_cases.process_xml import ProcessXmlUseCase

logger = logging.getLogger(__name__)

_queue: asyncio.Queue = asyncio.Queue()


def get_queue() -> asyncio.Queue:
    return _queue


def _peek_xml_filename(file_path: Path) -> Optional[str]:
    """Lee solo la tabla del ZIP para obtener el nombre del primer XML, sin descomprimir."""
    try:
        with zipfile.ZipFile(str(file_path)) as zf:
            xml_files = [
                n for n in zf.namelist()
                if n.lower().endswith('.xml') and not n.startswith(('__MACOSX/', '._'))
            ]
            if xml_files:
                return PurePosixPath(xml_files[0]).name
    except Exception:
        pass
    return None


class FileWrapper:
    """Envuelve un Path como UploadFile-compatible para ProcessXmlUseCase."""

    def __init__(self, path: Path):
        self.filename = path.name
        self._path = path

    async def read(self) -> bytes:
        return self._path.read_bytes()


async def process_queue_worker() -> None:
    """Worker asyncio que consume la cola y procesa cada ZIP."""
    logger.info("Worker de procesamiento de ZIPs iniciado")
    while True:
        file_path: Path = await _queue.get()
        try:
            await _process_single_file(file_path)
        except Exception as e:
            logger.error("Error inesperado procesando %s: %s", file_path.name, e)
        finally:
            _queue.task_done()


async def _process_single_file(file_path: Path) -> None:
    downloads_dir = file_path.parent
    processed_dir = downloads_dir / "processed"
    errors_dir = downloads_dir / "errors"
    processed_dir.mkdir(exist_ok=True)
    errors_dir.mkdir(exist_ok=True)

    # Obtener nombre del XML antes de procesar, disponible para todos los casos del log
    xml_filename = _peek_xml_filename(file_path)

    db = SessionLocal()
    try:
        rag_url = os.getenv("RAG_SERVICE_URL", "http://rag-service:8002")
        use_case = ProcessXmlUseCase(
            document_repo=DocumentRepository(db),
            issuer_repo=IssuerRepository(db),
            receiver_repo=ReceiverRepository(db),
            tax_repo=TaxRepository(db),
            concept_repo=ConceptRepository(db),
            rag_client=RagClient(base_url=rag_url),
        )
        log_repo = ProcessingLogRepository(db)

        result = await use_case.execute(FileWrapper(file_path))

        acc_status, acc_error = await _trigger_accounting(result["document_id"])
        log_repo.create(ProcessingLog(
            filename=file_path.name,
            xml_filename=xml_filename or result.get("filename"),
            status="added",
            document_id=result["document_id"],
            document_number=result["data"]["document_number"],
            accounting_status=acc_status,
            accounting_error=acc_error,
        ))
        shutil.move(str(file_path), str(processed_dir / file_path.name))
        logger.info("ZIP procesado → XML: %s — movido a processed/", xml_filename)

    except DuplicateEntityException as e:
        log_repo = ProcessingLogRepository(db)
        doc_number = e.message.split(": ")[-1] if ": " in e.message else ""
        log_repo.create(ProcessingLog(
            filename=file_path.name,
            xml_filename=xml_filename,
            status="duplicate",
            document_number=doc_number,
        ))
        shutil.move(str(file_path), str(processed_dir / file_path.name))
        logger.info("ZIP duplicado → XML: %s — movido a processed/", xml_filename)

    except Exception as e:
        try:
            log_repo = ProcessingLogRepository(db)
            log_repo.create(ProcessingLog(
                filename=file_path.name,
                xml_filename=xml_filename,
                status="error",
                error_message=str(e),
            ))
        except Exception:
            pass
        shutil.move(str(file_path), str(errors_dir / file_path.name))
        logger.error("Error procesando %s (XML: %s): %s — movido a errors/", file_path.name, xml_filename, e)

    finally:
        db.close()


async def _trigger_accounting(document_id: int):
    """Dispara la generación de asiento contable en llm-service (best-effort).
    Retorna (accounting_status, accounting_error)."""
    url = os.getenv("LLM_SERVICE_URL", "http://llm-service:8003")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{url}/api/v1/accounting/generate",
                json={"document_id": document_id},
            )
        if response.status_code in (200, 201):
            logger.info("Causación contable generada para documento %d", document_id)
            return "triggered", None
        else:
            msg = f"HTTP {response.status_code}: {response.text[:200]}"
            logger.warning("Error al generar causación para doc %d: %s", document_id, msg)
            return "error", msg
    except Exception as e:
        msg = str(e)
        logger.warning("No se pudo generar causación para doc %d: %s", document_id, msg)
        return "error", msg
