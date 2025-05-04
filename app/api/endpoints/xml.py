from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from app.utils.zip_handler import extract_zip_file
from app.utils.xml_parser import parse_xml
from typing import Optional

router = APIRouter()

ALLOWED_EXTENSIONS = {'xml', 'zip'}

@router.post("/readxml", response_model=dict)
async def read_xml(
    file: UploadFile = File(...)
):
    """
    Procesa un archivo ZIP o XML.
    
    Args:
        file: Archivo a procesar
    
    Returns:
        Diccionario con el resultado del procesamiento
        
    Raises:
        HTTPException: Si el formato del archivo no es válido
        HTTPException: Si hay un error al procesar el archivo
    """
    file_extension = file.filename.split('.')[-1].lower()
    return {"file_extension": file_extension}
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Formato de archivo no permitido. Solo se permiten archivos ZIP o XML."
        )
    
    if file_extension == 'zip':
        try:
            xml_content, filename = await extract_zip_file(file)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error interno al procesar el ZIP: {str(e)}"
            )
    else:
        xml_bytes = await file.read()
        xml_content = xml_bytes.decode('utf-8')
        filename = file.filename

    try:
        xml_data = parse_xml(xml_content)
        if not xml_data:
            raise ValueError("Error al parsear el XML. Verifique el contenido del archivo.")
        
        return {
            "status": "success",
            "data": xml_data,
            "filename": filename
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error al procesar el XML: {str(e)}"
        )
