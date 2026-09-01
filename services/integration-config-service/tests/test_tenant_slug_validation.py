"""Validación del slug de tenant antes de interpolarlo en el DSN (defensa en profundidad).

El slug llega de un claim del JWT o de una llamada interna y termina concatenado en la URL
de conexión (`abacus_t_{slug}`). Un valor con caracteres de sintaxis de URL o de control podría
alterar el destino de la conexión, así que se restringe al formato del aprovisionamiento.
"""

import pytest
from app.infrastructure.config.tenant_connection_manager import _validated_slug


@pytest.mark.parametrize("slug", ["ikbo", "empresa_2", "t123", "abc_def_9"])
def test_acepta_slugs_validos(slug):
    assert _validated_slug(slug) == slug


@pytest.mark.parametrize(
    "slug",
    [
        "",
        "IKBO",  # mayúsculas
        "ikbo-2",  # guion medio
        "ikbo 2",  # espacio
        "ikbo/otro",  # separador de path/URL
        "ikbo?x=1",  # query
        "ikbo;drop",  # separador de sentencias
        "ikbo\n",  # salto de línea
        "abacus_t_x@host",  # arroba de DSN
    ],
)
def test_rechaza_slugs_invalidos(slug):
    with pytest.raises(ValueError):
        _validated_slug(slug)
