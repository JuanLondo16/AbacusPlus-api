"""Respuesta del diagnóstico fiscal, pensada para leerse sin conocer la API de SIIGO."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RetencionDeEmpresaResponse(BaseModel):
    clave: str = Field(
        ..., description="Campo del perfil fiscal.", examples=["agente_retencion_ica"]
    )
    etiqueta: str = Field(..., description="Nombre de la retención.", examples=["Retención de ICA"])
    declarada_en_abacus: bool = Field(..., description="Marcada en el perfil fiscal de la empresa.")
    habilitada_en_siigo: Optional[bool] = Field(
        None,
        description=(
            "Bandera del comprobante de compra en SIIGO. `null` cuando la API no expone "
            "ninguna para esa retención, que es el caso de la retención en la fuente."
        ),
    )
    coincide: bool = Field(..., description="False si hay que corregir algo.")
    sin_soporte_en_la_api: bool = Field(
        ..., description="True si SIIGO no puede recibir esa retención por documento."
    )
    recomendacion: str = Field(..., description="Qué hacer, en términos accionables.")


class TerceroResponse(BaseModel):
    nit: str
    nombre: str
    existe_en_siigo: bool = Field(..., description="False si el tercero no está creado en SIIGO.")
    en_abacus: list[str] = Field(default_factory=list, description="Códigos según Abacus.")
    en_siigo: list[str] = Field(default_factory=list, description="Códigos según SIIGO.")
    faltan_en_siigo: list[str] = Field(default_factory=list)
    sobran_en_siigo: list[str] = Field(default_factory=list)
    afecta_retencion: bool = Field(
        ...,
        description=(
            "True si la diferencia cambia si se le practica retención en la fuente: es el "
            "código O-15, y es la única con efecto directo sobre dinero."
        ),
    )
    recomendacion: str


class FiscalDiagnosisResponse(BaseModel):
    generado_en: datetime
    comprobante_id: Optional[int] = Field(
        None, description="Tipo de comprobante de compra contrastado en SIIGO."
    )
    empresa: list[RetencionDeEmpresaResponse] = Field(default_factory=list)
    terceros: list[TerceroResponse] = Field(default_factory=list)
    terceros_revisados: int = 0
    terceros_con_diferencias: int = 0
    advertencias: list[str] = Field(
        default_factory=list,
        description="Motivos por los que el diagnóstico puede estar incompleto.",
    )
