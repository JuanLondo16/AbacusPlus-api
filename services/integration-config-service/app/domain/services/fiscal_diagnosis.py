"""Contraste entre lo que Abacus sabe de la situación fiscal y lo que SIIGO tiene configurado.

Solo compara: **no escribe nada en SIIGO**. No es una limitación de la implementación sino del
contrato, y conviene dejarlo escrito para que nadie lo reintente sin conocer el riesgo:

- La configuración de la empresa y del comprobante **no es escribible**. De los nueve recursos
  del grupo «Catálogos» —Tipos de Comprobante e Impuestos incluidos— todos exponen únicamente
  `GET`. No existe `/v1/company` ni `/v1/settings`.
- El maestro de terceros **sí** admite `PUT`, pero reemplaza el registro completo: «debe
  enviar igual los campos como en su creación porque remplaza los datos. Si hay un campo vacio
  quedara vacio en Nube». Y `GET /v1/customers` no devuelve `commercial_name`, `comments`,
  `seller_id` ni `collector_id`, así que un ciclo leer-modificar-escribir los borraría. Al no
  devolverlos, tampoco se puede comprobar de antemano si tenían datos: el riesgo no es medible
  ni reversible.

Detectar la discrepancia sí es seguro, y resuelve el problema real: saber qué hay que corregir
en SIIGO y por qué una retención no se está practicando, sin descubrirlo documento a documento.

Este módulo es **puro**: no consulta la base ni la API. Recibe los datos ya obtenidos y aplica
las reglas, de modo que se puede probar entero sin red ni base de datos.
"""

from dataclasses import dataclass, field
from typing import Optional

# ── Terceros ──────────────────────────────────────────────────────────────────

#: Códigos de responsabilidad fiscal que documenta `POST /v1/customers`.
RESPONSABILIDADES = {
    "R-99-PN": "No Aplica - Otros",
    "O-13": "Gran contribuyente",
    "O-15": "Autorretenedor",
    "O-23": "Agente de retención IVA",
    "O-47": "Régimen simple de tributación",
}

#: El único código con consecuencia contable directa: a un autorretenedor no se le practica
#: retención en la fuente. Si Abacus lo sabe y SIIGO no, SIIGO retendrá a quien no debe.
CODIGO_AUTORRETENEDOR = "O-15"


@dataclass
class DiferenciaDeTercero:
    """Qué difiere, para un proveedor, entre lo que sabe Abacus y lo que tiene SIIGO."""

    nit: str
    nombre: str = ""
    #: False cuando el tercero no existe en SIIGO. No es una diferencia: es una ausencia, y se
    #: informa aparte porque su solución es otra —crearlo— y no corregir un código.
    existe_en_siigo: bool = True
    en_abacus: set = field(default_factory=set)
    en_siigo: set = field(default_factory=set)

    @property
    def faltan_en_siigo(self) -> set:
        """Códigos que Abacus tiene y SIIGO no: los que habría que añadir allí."""
        return self.en_abacus - self.en_siigo

    @property
    def sobran_en_siigo(self) -> set:
        """Códigos que SIIGO tiene y Abacus no.

        No se presume que Abacus tenga razón: el RUT de la factura puede estar desactualizado
        y SIIGO reflejar una corrección posterior del contador.
        """
        return self.en_siigo - self.en_abacus

    @property
    def coincide(self) -> bool:
        return self.existe_en_siigo and not self.faltan_en_siigo and not self.sobran_en_siigo

    @property
    def afecta_retencion(self) -> bool:
        """True si la diferencia cambia si a este tercero se le retiene o no."""
        return CODIGO_AUTORRETENEDOR in (self.faltan_en_siigo | self.sobran_en_siigo)


def codigos_de_abacus(tipo_contribuyente: Optional[str]) -> set:
    """Códigos declarados en Abacus, desde el texto de `issuers.tipo_contribuyente`.

    Se guardan separados por punto y coma —«O-13;O-15;O-23»—, tal como los devuelve el RUT de
    la factura. Lo que no sea un código conocido se descarta en lugar de arrastrarlo: no puede
    compararse con nada y solo ensuciaría el informe.
    """
    if not tipo_contribuyente:
        return set()
    crudo = str(tipo_contribuyente).replace(",", ";")
    return {p.strip().upper() for p in crudo.split(";") if p.strip().upper() in RESPONSABILIDADES}


def codigos_de_siigo(fiscal_responsibilities) -> set:
    """Códigos que SIIGO reporta, desde el `fiscal_responsibilities` de `GET /v1/customers`."""
    if not isinstance(fiscal_responsibilities, list):
        return set()
    codigos = set()
    for item in fiscal_responsibilities:
        if isinstance(item, dict):
            codigo = str(item.get("code") or "").strip().upper()
            if codigo:
                codigos.add(codigo)
    return codigos


def comparar_tercero(nit, nombre, tipo_contribuyente, tercero_siigo) -> DiferenciaDeTercero:
    """Diferencia para un tercero. `tercero_siigo` es None si no existe en SIIGO."""
    en_abacus = codigos_de_abacus(tipo_contribuyente)
    if tercero_siigo is None:
        return DiferenciaDeTercero(
            nit=str(nit or ""), nombre=nombre or "", existe_en_siigo=False, en_abacus=en_abacus
        )
    return DiferenciaDeTercero(
        nit=str(nit or ""),
        nombre=nombre or "",
        en_abacus=en_abacus,
        en_siigo=codigos_de_siigo(tercero_siigo.get("fiscal_responsibilities")),
    )


# ── Empresa ───────────────────────────────────────────────────────────────────

#: Qué bandera del comprobante de compra respalda cada retención del perfil de la empresa.
#:
#: `GET /v1/document-types?type=FC` devuelve `reteiva` y `reteica` para el comprobante, y la
#: documentación dice que de esa configuración salen los tipos utilizables: «De acuerdo a la
#: configuración del comprobante en el menú Configuración > Transacciones > Facturas, sección
#: Datos tributarios, puedes utilizar los siguientes tipos de retenciones».
#:
#: La retención en la fuente NO tiene bandera equivalente, y ese es justo el hallazgo que este
#: diagnóstico debe hacer visible: se puede declarar en Abacus y no existe forma de que SIIGO
#: la reciba por documento.
BANDERA_POR_RETENCION = {
    "agente_retencion_iva": "reteiva",
    "agente_retencion_ica": "reteica",
    "agente_retencion_renta": None,
}

ETIQUETA_POR_RETENCION = {
    "agente_retencion_iva": "Retención de IVA (ReteIVA)",
    "agente_retencion_ica": "Retención de ICA",
    "agente_retencion_renta": "Retención en la fuente (renta)",
}


@dataclass
class DiferenciaDeEmpresa:
    """Estado de una retención declarada en el perfil de la empresa frente a SIIGO."""

    clave: str
    etiqueta: str
    declarada_en_abacus: bool
    #: None cuando SIIGO no expone bandera para esa retención — el caso de la retefuente.
    habilitada_en_siigo: Optional[bool]

    @property
    def sin_soporte_en_la_api(self) -> bool:
        """True si SIIGO no ofrece forma de recibir esa retención por documento."""
        return self.habilitada_en_siigo is None

    @property
    def coincide(self) -> bool:
        if self.sin_soporte_en_la_api:
            # Solo coincide si tampoco se declara en Abacus: declararla y no poder enviarla
            # es precisamente la discrepancia que hay que mostrar.
            return not self.declarada_en_abacus
        return self.declarada_en_abacus == self.habilitada_en_siigo


def comparar_empresa(perfil, comprobante) -> list:
    """Contrasta el perfil fiscal de la empresa con la configuración del comprobante.

    `perfil` es el registro de `tenant_fiscal_profile`; `comprobante` es el tipo de comprobante
    de compra devuelto por SIIGO, o None si no se pudo consultar.
    """
    diferencias = []
    for clave, bandera in BANDERA_POR_RETENCION.items():
        declarada = bool(getattr(perfil, clave, False)) if perfil is not None else False
        if bandera is None:
            habilitada = None
        elif comprobante is None:
            # Sin la configuración de SIIGO no se puede afirmar nada; se omite en vez de
            # suponer que está deshabilitada y generar una alerta falsa.
            continue
        else:
            habilitada = bool(comprobante.get(bandera, False))
        diferencias.append(
            DiferenciaDeEmpresa(
                clave=clave,
                etiqueta=ETIQUETA_POR_RETENCION[clave],
                declarada_en_abacus=declarada,
                habilitada_en_siigo=habilitada,
            )
        )
    return diferencias
