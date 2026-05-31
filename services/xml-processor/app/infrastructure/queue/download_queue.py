import asyncio
import contextlib
import logging
import os
import re
import shutil
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional

import httpx

from app.application.use_cases.process_xml import ProcessXmlUseCase
from app.domain.exceptions.base import DuplicateEntityException
from app.infrastructure.clients.rag_client import RagClient
from app.infrastructure.config.database import SessionLocal
from app.infrastructure.persistence.models.processing_log import ProcessingLog
from app.infrastructure.persistence.repositories.concept_repository import ConceptRepository
from app.infrastructure.persistence.repositories.document_repository import DocumentRepository
from app.infrastructure.persistence.repositories.issuer_repository import IssuerRepository
from app.infrastructure.persistence.repositories.processing_log_repository import (
    ProcessingLogRepository,
)
from app.infrastructure.persistence.repositories.receiver_repository import ReceiverRepository
from app.infrastructure.persistence.repositories.tax_repository import TaxRepository
from app.infrastructure.queue.job_progress_store import JobProgressStore

logger = logging.getLogger(__name__)

# La cola transporta tuplas (Path, job_id | None).
# job_id es None cuando el item fue encolado por process-downloads (modo legacy).
_queue: asyncio.Queue = asyncio.Queue()

_progress_store: Optional[JobProgressStore] = None


def get_queue() -> asyncio.Queue:
    return _queue


def get_progress_store() -> JobProgressStore:
    global _progress_store
    if _progress_store is None:
        _progress_store = JobProgressStore(redis_url=os.getenv("REDIS_URL", "redis://redis:6379"))
    return _progress_store


def _peek_xml_filename(file_path: Path) -> Optional[str]:
    """Lee solo la tabla del ZIP para obtener el nombre del primer XML, sin descomprimir."""
    with contextlib.suppress(Exception), zipfile.ZipFile(str(file_path)) as zf:
        xml_files = [
            n
            for n in zf.namelist()
            if n.lower().endswith(".xml") and not n.startswith(("__MACOSX/", "._"))
        ]
        if xml_files:
            return PurePosixPath(xml_files[0]).name
    return None


def _sanitize_name(text: str) -> str:
    """Elimina caracteres especiales y normaliza el texto para usar en nombres de archivo."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_pdf_name(
    document_date, document_type: str, document_number: str, issuer_name: str
) -> str:
    """
    Construye el nombre del PDF con la nomenclatura:
    IKB - DOCU - AAAAMMDD - V01 - {tipo_documento} {numero_documento} {tercero}
    """
    try:
        date_str = document_date.strftime("%Y%m%d")
    except Exception:
        date_str = str(document_date).replace("-", "")[:8]

    doc_type = _sanitize_name(document_type or "")
    doc_number = _sanitize_name(document_number or "")
    issuer = _sanitize_name(issuer_name or "")
    suffix = " ".join(part for part in [doc_type, doc_number, issuer] if part).strip()
    return f"IKB - DOCU - {date_str} - V01 - {suffix}.pdf"


def _extract_files_to_processed(file_path: Path, processed_dir: Path, document_data: dict) -> None:
    """
    Descomprime el ZIP y:
    - Deja el XML en processed/xml/{nombre_original}.xml
    - Deja el PDF en processed/pdf/{nomenclatura_IKB}.pdf
    """
    pdf_dir = processed_dir / "pdf"
    xml_dir = processed_dir / "xml"
    pdf_dir.mkdir(exist_ok=True)
    xml_dir.mkdir(exist_ok=True)

    try:
        with zipfile.ZipFile(str(file_path)) as zf:
            for member in zf.namelist():
                if member.startswith(("__MACOSX/", "._")):
                    continue
                name_lower = member.lower()
                member_name = PurePosixPath(member).name

                if name_lower.endswith(".xml"):
                    dest = xml_dir / member_name
                    dest.write_bytes(zf.read(member))
                    logger.info("XML extraído → %s", dest)

                elif name_lower.endswith(".pdf"):
                    pdf_name = _build_pdf_name(
                        document_data.get("date"),
                        document_data.get("document_type", ""),
                        document_data.get("document_number", ""),
                        document_data.get("issuer_name", ""),
                    )
                    dest = pdf_dir / pdf_name
                    dest.write_bytes(zf.read(member))
                    logger.info("PDF extraído y renombrado → %s", dest)

    except Exception as e:
        logger.warning("No se pudieron extraer archivos del ZIP %s: %s", file_path.name, e)


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
        item = await _queue.get()
        # Soporta tanto tuplas (path, job_id) como paths sueltos (compatibilidad)
        if isinstance(item, tuple):
            file_path, job_id = item
        else:
            file_path, job_id = item, None

        try:
            await _process_single_file(file_path, job_id)
        except Exception as e:
            logger.error("Error inesperado procesando %s: %s", file_path.name, e)
        finally:
            _queue.task_done()


async def _process_single_file(file_path: Path, job_id: Optional[str]) -> None:
    downloads_dir = file_path.parent
    processed_dir = downloads_dir / "processed"
    errors_dir = downloads_dir / "errors"
    processed_dir.mkdir(exist_ok=True)
    errors_dir.mkdir(exist_ok=True)

    progress = get_progress_store() if job_id else None
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

        _extract_files_to_processed(file_path, processed_dir, result["data"])

        acc_status, acc_error = await _trigger_accounting(result["document_id"])

        log_repo.create(
            ProcessingLog(
                filename=file_path.name,
                xml_filename=xml_filename or result.get("filename"),
                status="added",
                document_id=result["document_id"],
                document_number=result["data"]["document_number"],
                accounting_status=acc_status,
                accounting_error=acc_error,
            )
        )
        shutil.move(str(file_path), str(processed_dir / file_path.name))
        logger.info("ZIP procesado → XML: %s — movido a processed/", xml_filename)

        if progress:
            await progress.mark_xml_done(job_id, "added", document_id=result["document_id"])
            await progress.mark_accounting_done(job_id, acc_status or "error", error=acc_error)

    except DuplicateEntityException as e:
        log_repo = ProcessingLogRepository(db)
        doc_number = e.message.split(": ")[-1] if ": " in e.message else ""

        existing_doc = DocumentRepository(db).get_by_document_number(doc_number)
        acc_status, acc_error = None, None
        if existing_doc:
            already_has_entry = await _has_accounting_entry(existing_doc.id)
            if not already_has_entry:
                logger.info("Documento duplicado %s sin causación — generando...", doc_number)
                acc_status, acc_error = await _trigger_accounting(existing_doc.id)
            else:
                logger.info("Documento duplicado %s ya tiene causación — omitiendo", doc_number)

        log_repo.create(
            ProcessingLog(
                filename=file_path.name,
                xml_filename=xml_filename,
                status="duplicate",
                document_number=doc_number,
                accounting_status=acc_status,
                accounting_error=acc_error,
            )
        )
        shutil.move(str(file_path), str(processed_dir / file_path.name))
        logger.info("ZIP duplicado → XML: %s — movido a processed/", xml_filename)

        if progress:
            await progress.mark_xml_done(
                job_id, "duplicate", document_id=existing_doc.id if existing_doc else None
            )
            if acc_status:
                await progress.mark_accounting_done(job_id, acc_status, error=acc_error)

    except Exception as e:
        with contextlib.suppress(Exception):
            log_repo = ProcessingLogRepository(db)
            log_repo.create(
                ProcessingLog(
                    filename=file_path.name,
                    xml_filename=xml_filename,
                    status="error",
                    error_message=str(e),
                )
            )
        shutil.move(str(file_path), str(errors_dir / file_path.name))
        logger.error(
            "Error procesando %s (XML: %s): %s — movido a errors/", file_path.name, xml_filename, e
        )

        if progress:
            await progress.mark_xml_done(job_id, "error", error=str(e))

    finally:
        db.close()


async def _has_accounting_entry(document_id: int) -> bool:
    """Consulta llm-service para saber si el documento ya tiene un asiento contable."""
    url = os.getenv("LLM_SERVICE_URL", "http://llm-service:8003")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{url}/api/v1/accounting/entries/{document_id}")
        if response.status_code == 200:
            data = response.json()
            return data.get("accounting_entry") is not None
    except Exception as e:
        logger.warning("No se pudo verificar causación para doc %d: %s", document_id, e)
    return False


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
