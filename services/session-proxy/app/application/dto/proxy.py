from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

#: Métodos que el proxy acepta reenviar. La descripción del endpoint ya prometía un 400 para
#: cualquier otro, pero nada lo comprobaba: llegaba tal cual al cliente HTTP.
_METODOS_PERMITIDOS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


class ProxyRequest(BaseModel):
    token: str = Field(..., description="Token de autenticación DIAN")
    method: str = Field(..., description="Método HTTP: GET, POST, PUT, DELETE, PATCH")
    path: str = Field(..., description="Ruta relativa al EXTERNAL_BASE_URL, ej: /api/facturas")
    body: Optional[dict[str, Any]] = Field(default=None)
    params: Optional[dict[str, Any]] = Field(default=None)

    @field_validator("method")
    @classmethod
    def _validar_metodo(cls, valor: str) -> str:
        normalizado = valor.strip().upper()
        if normalizado not in _METODOS_PERMITIDOS:
            raise ValueError(
                f"Método HTTP no permitido: {valor!r}. "
                f"Use uno de: {', '.join(sorted(_METODOS_PERMITIDOS))}."
            )
        return normalizado

    @field_validator("path")
    @classmethod
    def _validar_path(cls, valor: str) -> str:
        """Obliga a que la ruta sea realmente relativa al portal configurado.

        El caso de uso arma la URL concatenando: `EXTERNAL_BASE_URL + path`. Sin validar,
        `path` decide el destino final de una petición que viaja con el token de la DIAN del
        cliente dentro:

        * `path = ".evil.com/recoger"` produce `https://catalogo-vpfe.dian.gov.co.evil.com/…`
          —un dominio ajeno que solo *parece* el de la DIAN— y le entrega el token.
        * `path = "@evil.com/"` o `"//evil.com/"` redirigen igualmente fuera del portal.
        * Un `path` absoluto (`http://169.254.169.254/…`) apuntaría a la red interna, incluido
          el servicio de metadatos del proveedor de nube.

        Exigir que empiece por una sola `/` y no contenga `\\`, `@` ni `..` deja la ruta atada
        al host de `EXTERNAL_BASE_URL`, que es lo único que este endpoint debe poder alcanzar.
        """
        ruta = valor.strip()
        if not ruta.startswith("/"):
            raise ValueError("La ruta debe ser relativa y empezar por '/'.")
        # `//host` es una URL protocol-relative: el navegador y httpx la resuelven contra otro
        # host, no contra el configurado.
        if ruta.startswith("//"):
            raise ValueError("La ruta no puede empezar por '//'.")
        if "\\" in ruta:
            raise ValueError("La ruta no puede contener '\\'.")
        if "@" in ruta.split("?", 1)[0]:
            raise ValueError("La ruta no puede contener '@'.")
        if ".." in ruta:
            raise ValueError("La ruta no puede contener '..'.")
        return ruta


class ProxyResponse(BaseModel):
    status_code: int
    body: Any
    headers: dict[str, str] = Field(default_factory=dict)
    request_body: Optional[dict[str, Any]] = Field(default=None)
