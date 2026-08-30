"""Diagnóstico fiscal: qué difiere entre la configuración de Abacus y la de SIIGO."""

from fastapi import APIRouter, Depends, Query, status

from app.application.dto.fiscal_diagnosis import (
    FiscalDiagnosisResponse,
    RetencionDeEmpresaResponse,
    TerceroResponse,
)
from app.application.use_cases.diagnose_fiscal_setup import (
    LIMITE_POR_DEFECTO,
    DiagnoseFiscalSetupUseCase,
)
from app.dependencies import get_diagnose_fiscal_setup_use_case
from app.domain.services.fiscal_diagnosis import RESPONSABILIDADES
from app.infrastructure.config.auth_dependency import require_write

router = APIRouter()


def _recomendacion_empresa(d) -> str:
    """Qué hacer con esta retención, en términos que no exijan conocer la API."""
    if d.sin_soporte_en_la_api:
        if d.declarada_en_abacus:
            return (
                "SIIGO no admite recibir la retención en la fuente por documento: no existe "
                "campo para ella en la API ni bandera en el comprobante. Debe configurarse "
                "en SIIGO, en la ficha de cada proveedor, para que SIIGO la practique."
            )
        return "No se practica y SIIGO tampoco la recibiría por documento."
    if d.coincide:
        return "Configuración alineada."
    if d.declarada_en_abacus:
        return (
            "Está declarada en Abacus pero el comprobante de compra de SIIGO no la tiene "
            "habilitada. Actívela en SIIGO: Configuración › Transacciones › Facturas › "
            "sección Datos tributarios."
        )
    return (
        "El comprobante de SIIGO la tiene habilitada pero el perfil fiscal de Abacus no la "
        "declara. Revise cuál de los dos refleja la realidad."
    )


def _recomendacion_tercero(d) -> str:
    if not d.existe_en_siigo:
        return "El tercero no existe en SIIGO. Créelo antes de contabilizar sus facturas."
    if d.coincide:
        return "Responsabilidades fiscales alineadas."
    partes = []
    if d.faltan_en_siigo:
        nombres = ", ".join(
            f"{c} ({RESPONSABILIDADES.get(c, c)})" for c in sorted(d.faltan_en_siigo)
        )
        partes.append(f"Falta declarar en SIIGO: {nombres}.")
    if d.sobran_en_siigo:
        nombres = ", ".join(
            f"{c} ({RESPONSABILIDADES.get(c, c)})" for c in sorted(d.sobran_en_siigo)
        )
        partes.append(f"SIIGO declara y Abacus no: {nombres}.")
    if d.afecta_retencion:
        partes.append(
            "Afecta a la retención en la fuente: a un autorretenedor no se le practica, así "
            "que la diferencia cambia si se le retiene o no."
        )
    return " ".join(partes)


@router.get(
    "/integrations/siigo/fiscal-diagnosis",
    dependencies=[Depends(require_write)],
    response_model=FiscalDiagnosisResponse,
    status_code=status.HTTP_200_OK,
    summary="Contrastar la configuración fiscal de Abacus con la de SIIGO",
    description=(
        "**Operación de solo lectura.** No modifica nada en SIIGO.\n\n"
        "Compara dos cosas:\n\n"
        "1. **La empresa** — las retenciones declaradas en el perfil fiscal contra las "
        "banderas del comprobante de compra en SIIGO (`reteiva`, `reteica`), que es de donde "
        "SIIGO toma los tipos utilizables.\n"
        "2. **Los terceros** — las responsabilidades fiscales de `issuers` contra las que "
        "tiene cada proveedor en SIIGO. Interesa sobre todo el código `O-15` "
        "(Autorretenedor), porque a un autorretenedor no se le practica retención.\n\n"
        "**Por qué no escribe.** La configuración de la empresa y del comprobante no es "
        "escribible: los recursos de «Catálogos» de SIIGO exponen solo `GET`. El maestro de "
        "terceros sí admite `PUT`, pero reemplaza el registro completo y `GET /v1/customers` "
        "no devuelve `commercial_name`, `comments`, `seller_id` ni `collector_id`, de modo "
        "que sincronizar los borraría sin posibilidad de comprobarlo antes.\n\n"
        "**Consumo.** Cada tercero consultado gasta una petición del límite de 100 por "
        "minuto que impone SIIGO."
    ),
    response_description="Diferencias encontradas, con la acción recomendada para cada una.",
    responses={404: {"description": "No hay credencial activa de SIIGO."}},
)
def diagnose_fiscal_setup(
    solo_con_diferencias: bool = Query(
        True,
        description=(
            "Si es `true` (por defecto) omite los terceros que ya coinciden. El informe "
            "interesa por lo que no cuadra."
        ),
    ),
    limite: int = Query(
        LIMITE_POR_DEFECTO,
        ge=1,
        le=100,
        description=(
            "Máximo de terceros a consultar. Cada uno gasta una petición del cupo por minuto "
            "de SIIGO, así que el tope evita agotarlo con un solo diagnóstico."
        ),
    ),
    use_case: DiagnoseFiscalSetupUseCase = Depends(get_diagnose_fiscal_setup_use_case),
) -> FiscalDiagnosisResponse:
    resultado = use_case.execute(solo_con_diferencias=solo_con_diferencias, limite=limite)

    return FiscalDiagnosisResponse(
        generado_en=resultado.generado_en,
        comprobante_id=resultado.comprobante_id,
        empresa=[
            RetencionDeEmpresaResponse(
                clave=d.clave,
                etiqueta=d.etiqueta,
                declarada_en_abacus=d.declarada_en_abacus,
                habilitada_en_siigo=d.habilitada_en_siigo,
                coincide=d.coincide,
                sin_soporte_en_la_api=d.sin_soporte_en_la_api,
                recomendacion=_recomendacion_empresa(d),
            )
            for d in resultado.empresa
        ],
        terceros=[
            TerceroResponse(
                nit=d.nit,
                nombre=d.nombre,
                existe_en_siigo=d.existe_en_siigo,
                en_abacus=sorted(d.en_abacus),
                en_siigo=sorted(d.en_siigo),
                faltan_en_siigo=sorted(d.faltan_en_siigo),
                sobran_en_siigo=sorted(d.sobran_en_siigo),
                afecta_retencion=d.afecta_retencion,
                recomendacion=_recomendacion_tercero(d),
            )
            for d in resultado.terceros
        ],
        terceros_revisados=resultado.terceros_revisados,
        terceros_con_diferencias=sum(1 for d in resultado.terceros if not d.coincide),
        advertencias=resultado.advertencias,
    )
