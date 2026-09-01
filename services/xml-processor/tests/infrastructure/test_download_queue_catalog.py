"""La descarga masiva desde la DIAN debe procesar con el catálogo de impuestos delante.

Es la vía por la que entra casi todo. Construía el `ProcessXmlUseCase` sin cliente de
catálogo, de modo que `taxes` era siempre `[]` y ninguna línea quedaba enlazada a su impuesto.
El documento se guardaba sin error, así que el fallo no tenía síntoma: se descubrió midiendo
la base, donde de 152 líneas al 19 % solo una tenía `tax_id`.

Esta prueba fija que el caso de uso se construya con el cliente, y que el cliente hable por el
canal interno —el único que funciona sin usuario—.
"""

import inspect

from app.infrastructure.queue import download_queue


class TestLaDescargaMasivaRecibeElCatalogo:
    def test_construye_el_caso_de_uso_con_cliente_de_catalogo(self):
        """`ProcessXmlUseCase` se arma pasándole `integration_config_client`.

        Sin este argumento el caso de uso deja `self.integration_config_client = None` y salta
        la consulta entera, que es exactamente lo que ocurría.
        """
        fuente = inspect.getsource(download_queue._process_single_file)
        assert "integration_config_client" in fuente

    def test_el_cliente_se_construye_para_el_tenant_que_se_esta_procesando(self):
        """El cliente va con `tenant_slug`, no con un token que aquí no existe.

        La descarga corre en segundo plano: no hay JWT que pasar. Con `tenant_slug` el cliente
        usa la ruta interna y el `X-Internal-Secret`, que es la única que responde sin usuario.
        """
        fuente = inspect.getsource(download_queue._process_single_file)
        assert "tenant_slug=tenant_slug" in fuente

    def test_existe_un_constructor_del_cliente_de_catalogo(self):
        """Hay una función que centraliza la URL del servicio, como con el siigo-service."""
        assert hasattr(download_queue, "build_integration_config_client")

    def test_el_constructor_devuelve_un_cliente_por_la_ruta_interna(self, monkeypatch):
        """Construido con tenant, el cliente apunta a `/internal/taxes`."""
        monkeypatch.setenv("INTERNAL_SECRET", "secreto-de-prueba")
        cliente = download_queue.build_integration_config_client(tenant_slug="ikbo")
        assert cliente.taxes_path == "/internal/taxes"
        assert cliente.headers["X-Tenant-Slug"] == "ikbo"
