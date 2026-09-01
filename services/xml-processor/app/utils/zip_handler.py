import io
import xml.etree.ElementTree as ET  # noqa: S405 # nosemgrep: use-defused-xml — solo el tipo ParseError, el parseo usa defusedxml
import zipfile
from pathlib import Path
from typing import Optional

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as parse_xml_string


async def extract_zip_file(
    zip_file, max_file_size: int = 10 * 1024 * 1024
) -> tuple[str, Optional[str], bytes, Optional[bytes]]:
    """
    Extract the first XML file found in a ZIP, along with the raw bytes needed to keep an
    official backup of the invoice (RF-03: `documents.xml_data` / `documents.pdf_data`).

    Args:
        zip_file: Uploaded ZIP file (FastAPI UploadFile)
        max_file_size: Maximum allowed size (10MB by default)

    Returns:
        Tuple[xml_content, filename, xml_bytes, pdf_bytes]. `pdf_bytes` is None when the ZIP
        doesn't contain a PDF, or its content doesn't have a valid `%PDF-` signature — the
        same criterion the DIAN download queue already applies.

    Raises:
        ValueError: If no XML files found or file is too large
        zipfile.BadZipFile: If not a valid ZIP
    """
    try:
        zip_content = await zip_file.read()

        if len(zip_content) > max_file_size:
            raise ValueError(f"ZIP file exceeds maximum size of {max_file_size/1024/1024}MB")

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_ref:
            xml_files = [
                name
                for name in zip_ref.namelist()
                if name.lower().endswith(".xml") and not name.startswith(("__MACOSX/", "._"))
            ]

            if not xml_files:
                raise ValueError("No valid XML files found in the ZIP")

            xml_filename = xml_files[0]

            if any(part.startswith(("..", "~")) for part in Path(xml_filename).parts):
                raise ValueError("File name not allowed")

            with zip_ref.open(xml_filename) as xml_file:
                xml_bytes = xml_file.read()
                content = xml_bytes.decode("utf-8")

                try:
                    parse_xml_string(content)
                except ET.ParseError as exc:
                    raise ValueError("File does not contain valid XML") from exc
                except DefusedXmlException as exc:
                    # DTD o entidades: se descarta antes de seguir procesando el ZIP.
                    raise ValueError(f"XML rechazado por seguridad: {exc}") from exc

            # El ZIP de la DIAN puede traer también la representación gráfica oficial. Se
            # conserva junto al XML para que la carga manual quede respaldada igual que la
            # descarga automática (`infrastructure/queue/download_queue.py`), en vez de
            # depender de que alguien vuelva a la DIAN a buscarla.
            pdf_bytes: Optional[bytes] = None
            for name in zip_ref.namelist():
                if name.lower().endswith(".pdf") and not name.startswith(("__MACOSX/", "._")):
                    with zip_ref.open(name) as pdf_file:
                        data = pdf_file.read()
                    if data[:5] == b"%PDF-":
                        pdf_bytes = data
                        break

            return content, xml_filename, xml_bytes, pdf_bytes

    except zipfile.BadZipFile as exc:
        raise ValueError("File is not a valid ZIP") from exc
    except UnicodeDecodeError as exc:
        raise ValueError("XML file does not have valid UTF-8 encoding") from exc
