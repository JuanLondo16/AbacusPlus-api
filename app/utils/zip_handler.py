import zipfile
import io
import os
from pathlib import Path
from typing import Tuple, Optional
import xml.etree.ElementTree as ET

async def extract_zip_file(zip_file, max_file_size: int = 10 * 1024 * 1024) -> Tuple[str, Optional[str]]:
    """
    Extrae el primer archivo XML encontrado en un ZIP
    
    Args:
        zip_file: Archivo ZIP subido (FastAPI UploadFile)
        max_file_size: Tamaño máximo permitido (10MB por defecto)
    
    Returns:
        Tuple[contenido_xml, nombre_archivo]
    
    Raises:
        ValueError: Si no hay archivos XML o el archivo es muy grande
        zipfile.BadZipFile: Si no es un ZIP válido
    """
    try:
        # Leer el contenido del archivo en memoria
        zip_content = await zip_file.read()
        
        # Verificar tamaño máximo
        if len(zip_content) > max_file_size:
            raise ValueError(f"El archivo ZIP excede el tamaño máximo de {max_file_size/1024/1024}MB")
        
        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_ref:
            # Buscar archivos XML (case insensitive)
            xml_files = [name for name in zip_ref.namelist() 
                        if name.lower().endswith('.xml') and not name.startswith(('__MACOSX/', '._'))]
            
            if not xml_files:
                raise ValueError("No se encontraron archivos XML válidos en el ZIP")
            
            # Tomar el primer archivo XML encontrado
            xml_filename = xml_files[0]
            
            # Verificar path traversal
            if any(part.startswith(('..', '~')) for part in Path(xml_filename).parts):
                raise ValueError("Nombre de archivo no permitido")
            
            # Leer el contenido del XML
            with zip_ref.open(xml_filename) as xml_file:
                content = xml_file.read().decode('utf-8')
                
                # Validación básica de XML (opcional)
                try:
                    ET.fromstring(content)
                except ET.ParseError:
                    raise ValueError("El archivo no contiene XML válido")
                
                return content, xml_filename
    
    except zipfile.BadZipFile:
        raise ValueError("El archivo no es un ZIP válido")
    except UnicodeDecodeError:
        raise ValueError("El archivo XML no tiene codificación UTF-8 válida")