from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CostCenterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class TaxCatalogResponse(BaseModel):
    """RF-02: impuesto/retención para el selector.

    `ambito=linea` y `ambito=todos` (parcialmente) devuelven filas de `integration_taxes`;
    `ambito=retenciones` devuelve filas de `integration_retentions` — desde la migración del
    2026-08-31, cada retención `reteica` ya trae su municipio, concepto y base mínima, así
    que el selector puede distinguir entre varias tarifas de ReteICA sin cruzar ninguna otra
    tabla. Los campos de municipio quedan `null` para cualquier fila que no sea `reteica`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    percentage: float
    municipality_code: Optional[str] = Field(
        None,
        description="Código DANE del municipio. Solo presente si type='reteica'.",
        examples=["11001"],
    )
    municipality_name: Optional[str] = Field(
        None, description="Nombre del municipio. Solo en reteica.", examples=["Bogotá D.C."]
    )
    retention_concept: Optional[str] = Field(
        None,
        description="Concepto que fija la tarifa dentro del municipio. Solo en reteica.",
        examples=["servicios"],
    )
    minimum_base_uvt: Optional[float] = Field(
        None,
        description="Base mínima en UVT por debajo de la cual no se practica. Solo en reteica.",
        examples=[4.0],
    )


class PucAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    level: Optional[int] = None
    accepts_movements: Optional[bool] = Field(
        None,
        description=(
            "Si la cuenta admite imputación directa. Solo las cuentas hoja (auxiliares) "
            "la aceptan; las de clase, grupo, cuenta y subcuenta agrupan. `null` en "
            "catálogos importados antes de que el dato se proyectara."
        ),
        examples=[True],
    )


class RetentionFuenteRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    retention_concept: str
    taxpayer_type: str
    minimum_base_uvt: Optional[float] = None
    minimum_base_pesos: Optional[float] = None
    rate_percentage: float


class RetentionIcaRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    municipality_code: str
    municipality_name: Optional[str] = None
    #: Concepto de la operación que fija esta tarifa (servicios, compras, honorarios…).
    #: `todos` significa que aplica a cualquier concepto en ese municipio. Un municipio puede
    #: aparecer varias veces, una por concepto: es lo que permite que el sistema elija la
    #: tarifa correcta en vez de aplicar la misma a toda operación.
    retention_concept: str = "todos"
    percentage: float
    #: Tope en UVT por debajo del cual no se practica la retención. `None` = sin tope.
    #: Lo fija cada municipio: el ICA es territorial y no hay uniformidad nacional.
    minimum_base_uvt: Optional[float] = None


class ImportRetentionRatesResponse(BaseModel):
    fuente_loaded: int = Field(
        0,
        description="Cantidad de tarifas de ReteFuente cargadas (0 si el archivo no traía esa hoja).",
    )
    ica_loaded: int = Field(
        0,
        description="Cantidad de tarifas de ReteICA cargadas/actualizadas (0 si no traía esa hoja).",
    )


class CostCenterProjectionItem(BaseModel):
    """Centro de costo tal como lo entrega el catálogo sincronizado del proveedor externo.

    Refleja el contrato de `GET /v1/cost-centers` de SIIGO.
    """

    code: str = Field(..., description="Código del centro de costo.", examples=["13-1"])
    name: str = Field(..., description="Nombre del centro de costo.", examples=["Principal"])
    active: bool = Field(True, description="Estado del centro de costo en el proveedor.")


class CostCenterProjectionResponse(BaseModel):
    created: int = Field(..., description="Centros de costo creados localmente.")
    updated: int = Field(..., description="Centros actualizados o desactivados.")
    total: int = Field(..., description="Total de centros de costo activos tras la proyección.")


class PucAccountProjectionItem(BaseModel):
    """Cuenta contable tal como la entrega la importación de plan de cuentas."""

    code: str = Field(..., description="Código contable.", examples=["510505"])
    name: str = Field(..., description="Nombre de la cuenta.", examples=["Gastos de personal"])
    level: Optional[int] = Field(None, description="Nivel jerárquico de la cuenta.")
    active: bool = Field(True, description="Estado de la cuenta en el origen.")
    accepts_movements: Optional[bool] = Field(
        None,
        description=(
            "Si la cuenta admite movimiento. Lo calcula la importación detectando qué "
            "códigos son hoja del plan. `null` cuando el origen no lo informa."
        ),
        examples=[True],
    )


class PucAccountProjectionResponse(BaseModel):
    created: int = Field(..., description="Cuentas creadas localmente.")
    updated: int = Field(..., description="Cuentas actualizadas.")
    total: int = Field(..., description="Total de cuentas activas tras la proyección.")
