import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Optional


async def extract_zip_file(
    zip_file, max_file_size: int = 10 * 1024 * 1024
) -> tuple[str, Optional[str]]:
    """
    Extract the first XML file found in a ZIP.

    Args:
        zip_file: Uploaded ZIP file (FastAPI UploadFile)
        max_file_size: Maximum allowed size (10MB by default)

    Returns:
        Tuple[xml_content, filename]

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
                content = xml_file.read().decode("utf-8")

                try:
                    ET.fromstring(content)
                except ET.ParseError:
                    raise ValueError("File does not contain valid XML")

                return content, xml_filename

    except zipfile.BadZipFile:
        raise ValueError("File is not a valid ZIP")
    except UnicodeDecodeError:
        raise ValueError("XML file does not have valid UTF-8 encoding")
