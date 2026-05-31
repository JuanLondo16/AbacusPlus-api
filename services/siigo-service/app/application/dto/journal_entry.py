from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class JournalEntryLine(BaseModel):
    cuenta: str = Field(..., description="Codigo de cuenta PUC.", examples=["510505"])
    debito: Decimal = Field(..., description="Valor debito. 0 si es credito.", examples=[47900.00])
    credito: Decimal = Field(..., description="Valor credito. 0 si es debito.", examples=[0.00])
    tercero: Optional[str] = Field(
        None,
        description="NIT o identificacion del tercero sin guiones ni puntos.",
        examples=["900123456"],
    )
    tercero_tipo_id: str = Field(
        "NIT", description="Tipo de identificacion: NIT, CC, CE, PP, etc.", examples=["NIT"]
    )
    tercero_tipo_persona: str = Field(
        "Company", description="Tipo de persona SIIGO: Company o Person.", examples=["Company"]
    )
    tercero_sucursal: str = Field(
        "000",
        description="Codigo de sucursal del tercero (digito verificacion para NIT).",
        examples=["000"],
    )
    centro_costo: Optional[int] = Field(
        None, description="ID entero del centro de costo en SIIGO.", examples=[235]
    )
    descripcion: Optional[str] = Field(
        None, description="Descripcion de la linea.", examples=["Causacion factura FV-7674"]
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "cuenta": "510505",
                "debito": 47900.00,
                "credito": 0.00,
                "tercero": "900123456",
                "tercero_tipo_id": "NIT",
                "tercero_tipo_persona": "Company",
                "tercero_sucursal": "000",
                "centro_costo": None,
                "descripcion": "Causacion factura FV-7674",
            }
        }
    }


class SendJournalEntryRequest(BaseModel):
    account_key: str = Field(
        "default", description="Cuenta SIIGO configurada en credenciales.", examples=["default"]
    )
    voucher_document_id: int = Field(
        ...,
        description="ID del tipo de comprobante contable en SIIGO. Consultar /v1/document-types?type=CC.",
        examples=[8],
    )
    entry_date: date = Field(
        ..., description="Fecha del comprobante contable (YYYY-MM-DD).", examples=["2024-01-15"]
    )
    observations: Optional[str] = Field(
        None,
        description="Observaciones del comprobante.",
        examples=["Causacion FV-7674 - Proveedor ABC SAS"],
    )
    currency_code: str = Field("COP", description="Codigo de moneda ISO 4217.", examples=["COP"])
    exchange_rate: Decimal = Field(
        Decimal("1"), description="Tasa de cambio. 1 para COP.", examples=[1]
    )
    lines: list[JournalEntryLine] = Field(
        ..., description="Lineas del asiento contable. Debitos deben igualar creditos."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "account_key": "default",
                "voucher_document_id": 8,
                "entry_date": "2024-01-15",
                "observations": "Causacion FV-7674 - Proveedor ABC SAS NIT 900123456",
                "currency_code": "COP",
                "exchange_rate": 1,
                "lines": [
                    {
                        "cuenta": "510505",
                        "debito": 47900.00,
                        "credito": 0.00,
                        "tercero": "900123456",
                        "tercero_tipo_id": "NIT",
                        "tercero_tipo_persona": "Company",
                        "tercero_sucursal": "000",
                        "descripcion": "Gasto personal",
                    },
                    {
                        "cuenta": "220505",
                        "debito": 0.00,
                        "credito": 47900.00,
                        "tercero": "900123456",
                        "tercero_tipo_id": "NIT",
                        "tercero_tipo_persona": "Company",
                        "tercero_sucursal": "000",
                        "descripcion": "CxP proveedor",
                    },
                ],
            }
        }
    }


class SendJournalEntryResponse(BaseModel):
    status: str = Field(
        ..., description="Estado de la operacion: created o error.", examples=["created"]
    )
    siigo_id: Optional[str] = Field(
        None, description="ID del comprobante creado en SIIGO.", examples=["CC-2024-001"]
    )
    siigo_response: dict[str, Any] = Field(
        default_factory=dict, description="Respuesta completa de SIIGO."
    )
    message: Optional[str] = Field(
        None,
        description="Mensaje adicional o descripcion del error.",
        examples=["Comprobante creado exitosamente."],
    )

    model_config = {"from_attributes": True}
