from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Identificador único de la línea.")
    document_id: int = Field(..., description="ID del documento al que pertenece.")
    description: str = Field(..., description="Descripción del concepto facturado.")
    concept_description_id: int = Field(..., description="ID del concepto en el catálogo local.")
    quantity: float = Field(..., description="Cantidad.")
    unit: str = Field(..., description="Unidad de medida.")
    price: float = Field(..., description="Precio unitario.")
    subtotal: float = Field(..., description="Subtotal sin impuesto.")
    tax_type: str = Field(..., description="Porcentaje de impuesto como texto (ej. '19.0').")
    tax_value: float = Field(..., description="Valor del impuesto.")
    total: float = Field(..., description="Total de la línea (subtotal + impuesto).")
    concept_account_number: Optional[str] = Field(
        None, description="Cuenta PUC del catálogo de conceptos. Null si no tiene concepto asignado."
    )
    code: Optional[str] = Field(
        None, description="Código PUC asignado por el LLM. Null si aún no se ha procesado.", examples=["511500"]
    )
    type: str = Field(
        "Account",
        description="Tipo de ítem contable: Account, Product o FixedAsset.",
        examples=["Account"],
    )
    tax_id: Optional[int] = Field(
        None, description="ID del impuesto en integration_taxes. Null si no hubo coincidencia."
    )
    cost_center_id: Optional[int] = Field(
        None, description="ID del centro de costo asignado por historial. Null si no hay historial."
    )


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_name: str
    document_number: str
    date: date
    hour: str
    currency: str
    document_type: str
    uuid: str
    issuer_name: str
    issuer_nit: str
    issuer_phone: Optional[str] = None
    issuer_email: Optional[str] = None
    receiver_name: str
    receiver_nit: str
    receiver_phone: Optional[str] = None
    receiver_email: Optional[str] = None
    subtotal: float
    total_taxes: float
    retefuente: float = 0.0
    reteica: float = 0.0
    total: float
    register_at: datetime
    status: int
    payment_type_id: Optional[int] = Field(
        None, description="ID del medio de pago en integration_payment_types. Null si el emisor no tiene uno configurado."
    )
    details: list[DocumentDetailResponse] = []


class DocumentSummaryResponse(BaseModel):
    """Resumen de un documento para listados (sin líneas de detalle)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "document_number": "FE7674",
                "document_name": "factura_fe7674.xml",
                "document_type": "Factura Electrónica",
                "date": "2024-01-15",
                "issuer_name": "PROVEEDOR S.A.S",
                "issuer_nit": "900123456",
                "receiver_name": "MI EMPRESA S.A.S",
                "receiver_nit": "800987654",
                "subtotal": 100000.0,
                "total_taxes": 19000.0,
                "retefuente": 0.0,
                "reteica": 0.0,
                "total": 119000.0,
                "status": 100,
                "register_at": "2024-01-15T10:30:00",
            }
        },
    )

    id: int = Field(..., description="Identificador único del documento.")
    document_number: str = Field(
        ..., description="Número de la factura electrónica.", examples=["FE7674"]
    )
    document_name: str = Field(..., description="Nombre del archivo XML o ZIP procesado.")
    document_type: str = Field(
        ..., description="Tipo de documento DIAN.", examples=["Factura Electrónica"]
    )
    date: date
    issuer_name: str = Field(..., description="Razón social del emisor.")
    issuer_nit: str = Field(..., description="NIT del emisor.", examples=["900123456"])
    receiver_name: str = Field(..., description="Razón social del receptor.")
    receiver_nit: str = Field(..., description="NIT del receptor.", examples=["800987654"])
    subtotal: float = Field(..., description="Subtotal antes de impuestos.")
    total_taxes: float = Field(..., description="Total de impuestos (IVA).")
    retefuente: float = Field(..., description="Valor de retención en la fuente.")
    reteica: float = Field(..., description="Valor de reteICA.")
    total: float = Field(..., description="Valor total del documento.")
    status: int = Field(
        ...,
        description="Código de estado del documento. 0=Error, 100=Procesado, 200=Causado, 300=Aprobado, 400=Contabilizada.",
        examples=[100],
    )
    register_at: datetime = Field(..., description="Fecha y hora de registro en el sistema.")
    payment_type_id: Optional[int] = Field(
        None,
        description="ID del medio de pago configurado para el emisor. Null si no tiene uno asignado.",
    )


class AccountingLineResponse(BaseModel):
    """Línea de un asiento contable (partida doble)."""

    id: int = Field(..., description="Identificador único de la línea.")
    cuenta: str = Field(..., description="Código de cuenta PUC.", examples=["220500"])
    nombre: str = Field(
        ..., description="Nombre de la cuenta PUC.", examples=["Proveedores nacionales"]
    )
    debito: float = Field(..., description="Valor al débito.", examples=[0.0])
    credito: float = Field(..., description="Valor al crédito.", examples=[119000.0])
    tercero: Optional[str] = Field(
        None, description="NIT del tercero relacionado.", examples=["900123456"]
    )
    centro_costo: Optional[str] = Field(None, description="Código del centro de costo.")
    descripcion: Optional[str] = Field(None, description="Descripción del movimiento contable.")


class AccountingEntryData(BaseModel):
    """Asiento contable generado por el LLM para un documento."""

    id: int = Field(..., description="Identificador único del asiento.")
    model_used: Optional[str] = Field(
        None, description="Modelo de OpenAI utilizado.", examples=["gpt-4o-mini"]
    )
    status: str = Field(..., description="Estado: `generated` o `error`.", examples=["generated"])
    lines: list[AccountingLineResponse] = Field(
        default_factory=list, description="Líneas del asiento (partida doble)."
    )
    created_at: datetime = Field(..., description="Fecha y hora de generación del asiento.")


class DocumentDetailWithAccountingResponse(BaseModel):
    """Detalle completo de un documento: lectura XML + asiento contable de causación."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "xml_reading": {
                    "id": 1,
                    "document_number": "FE7674",
                    "issuer_name": "PROVEEDOR S.A.S",
                    "total": 119000.0,
                    "details": [{"description": "Servicio X", "quantity": 1, "total": 119000.0}],
                },
                "accounting": {
                    "id": 5,
                    "model_used": "gpt-4o-mini",
                    "status": "generated",
                    "lines": [
                        {
                            "id": 1,
                            "cuenta": "220500",
                            "nombre": "Proveedores nacionales",
                            "debito": 0.0,
                            "credito": 119000.0,
                            "tercero": "900123456",
                        },
                        {
                            "id": 2,
                            "cuenta": "511500",
                            "nombre": "Gastos de servicios",
                            "debito": 119000.0,
                            "credito": 0.0,
                            "tercero": "",
                        },
                    ],
                    "created_at": "2024-01-15T11:00:00",
                },
            }
        }
    )

    xml_reading: DocumentResponse = Field(
        ...,
        description="Datos completos del documento procesado desde el XML DIAN, incluyendo cabecera y líneas de detalle.",
    )
    accounting: Optional[AccountingEntryData] = Field(
        None,
        description="Último asiento contable generado para el documento. Null si aún no se ha causado.",
    )


class DocumentDetailCodeUpdateItem(BaseModel):
    detail_id: int = Field(..., description="ID de la línea de detalle a actualizar.", examples=[42])
    code: str = Field(
        ..., description="Código PUC asignado por el LLM.", examples=["511500"]
    )
    type: str = Field(
        "Account",
        description="Tipo de ítem contable. Valores: Account, Product, FixedAsset.",
        examples=["Account"],
    )
    model_config = {"json_schema_extra": {"example": {"detail_id": 42, "code": "511500", "type": "Account"}}}


class DocumentDetailCodeUpdateResponse(BaseModel):
    updated: int = Field(..., description="Cantidad de líneas actualizadas.", examples=[3])


class DocumentStatusUpdateRequest(BaseModel):
    status: int = Field(
        ...,
        description=(
            "Código de estado destino. Valores soportados: "
            "200 (Causado — revierte aprobación, el documento debe estar en estado Aprobado)."
        ),
        examples=[200],
    )
    model_config = {"json_schema_extra": {"example": {"status": 200}}}


class ProcessXmlResponse(BaseModel):
    status: str
    data: dict
    document_id: int
    filename: str
