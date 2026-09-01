"""Filtro por rol del comprador: solo se ofrecen retenciones para las que la empresa es agente.

El perfil fiscal del tenant es autoritativo. Si no está configurado (default conservador), no
se filtra por rol para no vaciar las sugerencias.

Las candidatas llegan aquí ya clasificadas por `domain/services/tax_catalog.py`, que es quien
lee el catálogo de Impuestos. Por eso el impoconsumo no aparece en este fixture: nunca llega
a este filtro, porque no es una retención que el comprador pueda practicarle al proveedor.
"""

from app.application.use_cases.suggest_retentions import SuggestRetentionsUseCase

_CANDIDATES = [
    {"id": 1, "type": "Retefuente", "clase": "retefuente", "name": "Retefuente 10%"},
    {"id": 2, "type": "ReteICA", "clase": "reteica", "name": "ReteICA 9.66"},
    {"id": 3, "type": "ReteIVA", "clase": "reteiva", "name": "ReteIVA 15%"},
]


def _types(items):
    return {i["clase"] for i in items}


def test_sin_perfil_no_filtra():
    warnings: list[str] = []
    result = SuggestRetentionsUseCase._only_buyer_agent_types(_CANDIDATES, None, warnings)
    assert _types(result) == {"retefuente", "reteica", "reteiva"}
    assert warnings == []


def test_perfil_default_no_filtra():
    # Todo en falso = no configurado: no debe vaciar las sugerencias.
    profile = {
        "agente_retencion_renta": False,
        "agente_retencion_ica": False,
        "agente_retencion_iva": False,
        "autorretenedor_renta": False,
        "gran_contribuyente": False,
        "responsable_iva": False,
        "notas": None,
    }
    result = SuggestRetentionsUseCase._only_buyer_agent_types(_CANDIDATES, profile, [])
    assert _types(result) == {"retefuente", "reteica", "reteiva"}


def test_perfil_configurado_filtra_por_rol():
    # Agente de renta e ICA, pero NO de IVA: se cae ReteIVA.
    profile = {
        "agente_retencion_renta": True,
        "agente_retencion_ica": True,
        "agente_retencion_iva": False,
        "gran_contribuyente": True,
        "notas": None,
    }
    warnings: list[str] = []
    result = SuggestRetentionsUseCase._only_buyer_agent_types(_CANDIDATES, profile, warnings)
    assert _types(result) == {"retefuente", "reteica"}
    assert "reteiva" in warnings[0].lower()


def test_perfil_sin_ningun_agente_pero_configurado_filtra_las_tres():
    # Configurado (gran contribuyente) pero no es agente de ninguna retención: se caen las tres
    # y no queda nada que proponer.
    profile = {
        "agente_retencion_renta": False,
        "agente_retencion_ica": False,
        "agente_retencion_iva": False,
        "gran_contribuyente": True,
        "notas": None,
    }
    result = SuggestRetentionsUseCase._only_buyer_agent_types(_CANDIDATES, profile, [])
    assert result == []
