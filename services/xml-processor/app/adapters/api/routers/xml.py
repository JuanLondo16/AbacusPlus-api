from fastapi import APIRouter, Depends, File, UploadFile

from app.application.dto.document import ProcessXmlResponse
from app.application.use_cases.process_xml import ProcessXmlUseCase
from app.dependencies import get_process_xml_use_case

router = APIRouter()


@router.post(
    "/documents",
    response_model=ProcessXmlResponse,
    status_code=201,
    summary="Procesar factura DIAN (ZIP o XML)",
    description=(
        "Recibe un archivo ZIP o XML de factura electrónica DIAN, lo parsea, valida el NIT "
        "con dígito de verificación y persiste el documento en la base de datos. "
        "Simultáneamente indexa el contenido en el servicio RAG (best-effort: si RAG no está "
        "disponible el documento se guarda igual).\n\n"
        "**Formatos aceptados:** `.zip` (un XML dentro) o `.xml` directo.\n\n"
        "**Errores comunes:**\n"
        "- `400` — archivo no es ZIP/XML válido o no contiene un XML DIAN.\n"
        "- `409` — factura ya fue procesada anteriormente (número de documento duplicado)."
    ),
    response_description="Documento procesado con su ID asignado y datos extraídos.",
    responses={
        409: {"description": "Documento duplicado — ya existe en la base de datos."},
        400: {"description": "Archivo inválido o formato no soportado."},
    },
)
async def read_xml(
    file: UploadFile = File(..., description="Archivo ZIP o XML de factura electrónica DIAN"),
    use_case: ProcessXmlUseCase = Depends(get_process_xml_use_case),
):
    return await use_case.execute(file)
