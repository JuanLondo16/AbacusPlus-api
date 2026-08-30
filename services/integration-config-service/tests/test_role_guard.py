"""Un usuario de solo lectura no puede reescribir la configuración del cliente.

Este servicio guarda las credenciales de SIIGO y de Odoo, el perfil fiscal y los catálogos de
cuentas, impuestos y centros de costo: todo lo que determina cómo se contabiliza. Hasta ahora
comprobaba que quien llamaba estuviera autenticado, pero no qué rol tenía, así que un usuario
invitado como `viewer` podía sustituir las credenciales de la integración o reimportar el plan
de cuentas exactamente igual que un administrador.

Se prueba la dependencia directamente y no a través de un endpoint porque es el punto único
por el que pasan todas las escrituras: si `require_write` se comporta, cualquier ruta que la
declare queda cubierta.
"""

import pytest
from app.infrastructure.config.auth_dependency import (
    ROLES_ESCRITURA,
    TokenData,
    require_roles,
    require_write,
)
from fastapi import HTTPException


def _token(*roles: str) -> TokenData:
    return TokenData(
        {
            "sub": "u1",
            "tenant_id": "t1",
            "tenant_slug": "ikbo",
            "roles": list(roles),
            "email": "quien@ikbo.co",
        },
        raw_token="irrelevante",
    )


class TestQuienPuedeEscribir:
    @pytest.mark.parametrize("rol", sorted(ROLES_ESCRITURA))
    def test_los_roles_de_escritura_pasan(self, rol):
        token = _token(rol)
        assert require_write(token) is token

    def test_un_rol_de_escritura_basta_aunque_haya_otros(self):
        token = _token("viewer", "operator")
        assert require_write(token) is token


class TestQuienNo:
    def test_viewer_es_rechazado(self):
        """El caso que motiva todo esto: `viewer` promete solo lectura y debe cumplirlo."""
        with pytest.raises(HTTPException) as exc:
            require_write(_token("viewer"))
        assert exc.value.status_code == 403

    def test_un_token_sin_roles_es_rechazado(self):
        """Todo usuario recibe un rol al crearse; que no lo traiga no es un caso legítimo."""
        with pytest.raises(HTTPException) as exc:
            require_write(_token())
        assert exc.value.status_code == 403

    def test_un_rol_inventado_no_abre_la_puerta(self):
        with pytest.raises(HTTPException) as exc:
            require_write(_token("superadmin"))
        assert exc.value.status_code == 403


class TestElMensajeAyuda:
    def test_dice_que_roles_hacen_falta(self):
        """Sin esto, el contador ve un 403 pelado y no sabe qué pedirle a su administrador."""
        with pytest.raises(HTTPException) as exc:
            require_write(_token("viewer"))
        assert "operator" in exc.value.detail
        assert "tenant_admin" in exc.value.detail


class TestLaFabricaEsGenerica:
    def test_require_roles_respeta_la_lista_que_recibe(self):
        solo_admin = require_roles("tenant_admin")
        token = _token("tenant_admin")
        assert solo_admin(token) is token
        with pytest.raises(HTTPException):
            solo_admin(_token("operator"))
