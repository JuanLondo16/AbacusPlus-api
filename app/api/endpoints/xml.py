from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import JSONResponse
from app.utils.zip_handler import extract_zip_file
from app.utils.xml_parser import parse_xml
from app.utils.dian_dv import dv_calculate
from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.document import Document, DocumentDetail
from app.models.issuer import Issuer
from app.models.receiver import Receiver
from app.models.tax import Tax
from app.models.concept import ConceptDescription
from app.core.config import get_db
from datetime import datetime
from app.utils.search_concept import search_concept

router = APIRouter()

ALLOWED_EXTENSIONS = {'xml', 'zip'}

@router.post("/readxml", response_model=dict)
async def read_xml(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Procesa un archivo ZIP o XML.

    Args:
        file: Archivo a procesar
        db: Sesion de base de datos (inyectada por FastAPI)

    Returns:
        Diccionario con el resultado del procesamiento

    Raises:
        HTTPException: Si el formato del archivo no es válido
        HTTPException: Si hay un error al procesar el archivo
    """
    file_extension = file.filename.split('.')[-1].lower()
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

        db_document = db.query(Document).filter(Document.document_number == xml_data.get('numero_documento', '')).first()
        if db_document:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Documento {xml_data.get('numero_documento', '')} de {xml_data.get('emisor', '').get('nombre', '')} ya registrado"}
            )

        #Verificando Issuer
        db_issuer = db.query(Issuer).filter(Issuer.nit == xml_data.get('emisor', '').get('nit', '')).first()
        if not db_issuer:
            issuer = Issuer(
                name=xml_data.get('emisor', '').get('nombre', ''),
                nit=xml_data.get('emisor', '').get('nit', ''),
                dv=dv_calculate(xml_data.get('emisor', '').get('nit', '')),
                phone=xml_data.get('emisor', '').get('contacto', '').get('telefono', ''),
                email=xml_data.get('emisor', '').get('contacto', '').get('email', ''),
            )
            db.add(issuer)
            db.commit()
            db.refresh(issuer)

        #Verificando Receiver
        db_receiver = db.query(Receiver).filter(Receiver.nit == xml_data.get('receptor', '').get('nit', '')).first()
        if not db_receiver:
            receiver = Receiver(
                name=xml_data.get('receptor', '').get('nombre', ''),
                nit=xml_data.get('receptor', '').get('nit', ''),
                dv=dv_calculate(xml_data.get('receptor', '').get('nit', '')),
                phone=xml_data.get('receptor', '').get('contacto', '').get('telefono', ''),
                email=xml_data.get('receptor', '').get('contacto', '').get('email', ''),
            )
            db.add(receiver)
            db.commit()
            db.refresh(receiver)

        #Verificando impuesto
        db_tax = db.query(Tax).filter(Tax.receiver_nit == xml_data.get('receptor', '').get('nit', ''), Tax.tax == xml_data.get('impuestos', [])[0].get('nombre', '')).first()
        if not db_tax:
            tax = Tax(
                receiver_nit=xml_data.get('receptor', '').get('nit', ''),
                tax=xml_data.get('impuestos', [])[0].get('nombre', ''),
                percentage=xml_data.get('impuestos', [])[0].get('porcentaje', 0)
            )
            db.add(tax)
            db.commit()
            db.refresh(tax)

        # Crear nuevo documento
        document = Document(
            document_name=filename,
            document_number=xml_data.get('numero_documento', ''),
            date=datetime.strptime(xml_data.get('fecha_emision', ''), '%Y-%m-%d'),
            hour=xml_data.get('hora_emision', ''),
            currency=xml_data.get('moneda', ''),
            document_type=xml_data.get('tipo_documento', ''),
            uuid=xml_data.get('uuid', ''),
            issuer_name=xml_data.get('emisor', '').get('nombre', ''),
            issuer_nit=xml_data.get('emisor', '').get('nit', ''),
            issuer_phone=xml_data.get('emisor', '').get('contacto', '').get('telefono', ''),
            issuer_email=xml_data.get('emisor', '').get('contacto', '').get('email', ''),
            receiver_name=xml_data.get('receptor', '').get('nombre', ''),
            receiver_nit=xml_data.get('receptor', '').get('nit', ''),
            receiver_phone=xml_data.get('receptor', '').get('contacto', '').get('telefono', ''),
            receiver_email=xml_data.get('receptor', '').get('contacto', '').get('email', ''),
            subtotal=float(xml_data.get('totales', '').get('subtotal', 0)),
            total_taxes=float(xml_data.get('totales', '').get('total_impuestos', 0)),
            total=float(xml_data.get('totales', '').get('total', 0)),
            status='Procesado'
        )

        # Crear detalles del documento
        for item in xml_data.get('items', []):
            db_concept = search_concept(item.get('descripcion', ''), xml_data.get('receptor', '').get('nit', ''))
            if not db_concept:
                concept_description = ConceptDescription(
                    receiver_nit=xml_data.get('receptor', '').get('nit', ''),
                    description=item.get('descripcion', ''),
                )
                db.add(concept_description)
                db.commit()
                db.refresh(concept_description)
                concept_description_id = concept_description.id
            else:
                concept_description_id = db_concept.id

            detail = DocumentDetail(
                document_id=document.id,
                description=item.get('descripcion', ''),
                concept_description_id=concept_description_id,
                quantity=float(item.get('cantidad', 0)),
                unit=item.get('unidad_medida', ''),
                price=float(item.get('precio_unitario', 0)),
                subtotal=float(item.get('valor_total', 0)),
                tax_type=item.get('impuestos', [])[0].get('porcentaje', 0),
                tax_value=float(item.get('impuestos', [])[0].get('valor', 0)),
                total=float(item.get('valor_total', 0)) + float(item.get('impuestos', [])[0].get('valor', 0))
            )
            document.details.append(detail)

        db.add(document)
        db.commit()
        db.refresh(document)

        return {
            "status": "success",
            "data": {
                "id": document.id,
                "document_name": document.document_name,
                "document_number": document.document_number,
                "date": str(document.date),
                "issuer_name": document.issuer_name,
                "receiver_name": document.receiver_name,
                "total": document.total,
                "status": document.status,
                "details_count": len(document.details),
            },
            "document_id": document.id,
            "filename": filename
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Error al procesar el XML: {str(e)}"
        )
