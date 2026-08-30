"""El proxy solo puede alcanzar el portal configurado, nunca un destino elegido por quien llama.

`ProxyRequestUseCase` construye la URL concatenando `EXTERNAL_BASE_URL + path`. Mientras `path`
no se validaba, ese `+` era el punto donde quien llamaba decidía a qué servidor se enviaba una
petición que lleva dentro el token de la DIAN del cliente. Estos tests fijan el límite en el
DTO, que es donde se corta antes de que el caso de uso llegue a ver el valor.
"""

import pytest
from app.application.dto.proxy import ProxyRequest
from pydantic import ValidationError


def _construir(path: str) -> ProxyRequest:
    return ProxyRequest(token="t", method="GET", path=path)


class TestRutasRechazadas:
    @pytest.mark.parametrize(
        ("path", "motivo"),
        [
            # El caso central: `base + ".evil.com/"` produce un host que empieza igual que el
            # de la DIAN y termina en un dominio ajeno. No hay barra que lo separe, así que a
            # simple vista la URL resultante parece legítima.
            (".evil.com/recoger", "sufijo de dominio"),
            ("@evil.com/", "credenciales en la autoridad de la URL"),
            ("//evil.com/", "URL relativa al protocolo"),
            ("http://169.254.169.254/latest/meta-data/", "absoluta hacia la red interna"),
            ("https://evil.com/", "absoluta hacia el exterior"),
            ("\\\\evil.com\\x", "separador de Windows"),
            ("/api/../../admin", "traversal"),
        ],
    )
    def test_no_se_admite(self, path: str, motivo: str):
        with pytest.raises(ValidationError):
            _construir(path)


class TestRutasAdmitidas:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/facturas",
            "/User/AuthToken",
            "/Document/Search?tipo=01&pagina=2",
            "/",
        ],
    )
    def test_las_rutas_normales_del_portal_siguen_pasando(self, path: str):
        """La restricción no puede haberse llevado por delante el uso legítimo."""
        assert _construir(path).path == path


class TestMetodo:
    def test_se_normaliza_a_mayusculas(self):
        assert ProxyRequest(token="t", method="post", path="/x").method == "POST"

    @pytest.mark.parametrize("metodo", ["TRACE", "CONNECT", "OPTIONS", "FOO"])
    def test_se_rechaza_lo_que_no_esta_en_la_lista(self, metodo: str):
        """La documentación del endpoint ya prometía un 400 aquí; ahora se cumple."""
        with pytest.raises(ValidationError):
            ProxyRequest(token="t", method=metodo, path="/x")
