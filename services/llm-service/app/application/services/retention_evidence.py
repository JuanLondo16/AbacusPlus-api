"""RF-08 · Recuperación y consolidación de la evidencia que sustenta una sugerencia.

Antes había una sola recuperación: una búsqueda semántica con la frase «retenciones
aplicadas a {emisor}», tres resultados, concatenados y **recortados a 200 caracteres**. Con
ese recorte el historial no llegaba a informar nada —cabía media línea de un caso— y el
modelo, en la práctica, decidía sin precedentes aunque el sistema los tuviera indexados.

Aquí se recupera de cuatro fuentes y se mantienen SEPARADAS hasta el prompt, cada una con su
procedencia. La separación no es cosmética: es lo que impide el aprendizaje ciego. Un caso
histórico dice «así se resolvió una vez»; una tarifa oficial dice «así debe calcularse». Si
ambos llegan al modelo como texto indistinto, veinte casos parecidos acaban pesando más que
la tabla vigente, y el sistema se convierte en una máquina de repetir su propio pasado.

Jerarquía de confianza (de mayor a menor):

1. **Tablas tributarias estructuradas** — tarifas de ReteFuente por concepto y de ReteICA por
   municipio. Vinculantes: el porcentaje sale de aquí o no se propone la retención.
2. **Perfil fiscal de la empresa** — quién es agente de retención de qué. Vinculante para
   decidir si un tipo puede siquiera considerarse.
3. **Criterios del contador** — el cuestionario respondido, guardado como dato de cada
   empresa (`retention_criteria`) y editable sin desplegar. Guían la interpretación.
4. **Casos contabilizados similares** — precedentes reales. Evidencia, nunca norma.

La inferencia del modelo queda por debajo de las cuatro: solo actúa donde ninguna se
pronuncia, y el prompt se lo dice explícitamente.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.domain.knowledge import reteica_knowledge

logger = logging.getLogger(__name__)

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")

#: Longitud máxima de cada caso histórico dentro del prompt.
#:
#: El límite anterior (200 caracteres para los TRES casos juntos) hacía inútil la
#: recuperación. Un caso contabilizado ocupa unas 600–900 caracteres —cabecera, imputación y
#: retenciones con base y tarifa—, así que se acota por caso y no en bloque: recortar el
#: conjunto es lo que dejaba fuera precisamente las retenciones, que van al final del texto.
_MAX_CASO_CHARS = 900

#: Cuántos precedentes se recuperan. Tres bastan para mostrar un patrón sin inundar el
#: contexto; más allá, el modelo tiende a contar mayorías en vez de razonar el caso actual.
_TOP_K_CASOS = 3


@dataclass
class EvidenceBundle:
    """Evidencia recuperada, separada por procedencia y lista para el prompt."""

    #: Tarifas oficiales de ReteFuente por concepto (fuente estructurada, vinculante).
    tarifas_retefuente: list[dict] = field(default_factory=list)
    #: Tarifas oficiales de ReteICA por municipio (fuente estructurada, vinculante).
    tarifas_reteica: list[dict] = field(default_factory=list)
    #: Criterios documentados del contador.
    criterios_contador: list[dict] = field(default_factory=list)
    #: Causaciones contabilizadas similares (precedentes, no norma).
    casos_historicos: list[dict] = field(default_factory=list)
    #: Conocimiento CONCEPTUAL de ReteICA (contexto educativo). Escalón más bajo de la
    #: jerarquía: explica el tributo, no determina tarifas ni bases. Ver
    #: `domain/knowledge/reteica_knowledge.py`.
    conocimiento_conceptual: Optional[dict] = None
    #: Cómo se recuperaron los casos, para poder auditar la sugerencia después.
    traza_recuperacion: dict[str, Any] = field(default_factory=dict)

    def as_prompt_sections(self) -> dict[str, Any]:
        """Bloques del prompt, cada uno rotulado con su procedencia y su fuerza.

        Los rótulos van dentro del propio JSON, y no solo en las instrucciones del sistema,
        porque el modelo lee el dato y su etiqueta juntos. Decir «vinculante» al lado de la
        tabla y «precedente, no norma» al lado de los casos es lo que sostiene la jerarquía
        cuando ambos apuntan a respuestas distintas.
        """
        secciones: dict[str, Any] = {}
        if self.tarifas_retefuente:
            secciones["1_tarifas_oficiales_retefuente_por_concepto"] = {
                "fuerza": "VINCULANTE · tabla oficial cargada por el contador",
                "uso": "El porcentaje de ReteFuente sale de aquí. Si el concepto no aparece, no propongas ReteFuente.",
                "filas": self.tarifas_retefuente,
            }
        if self.tarifas_reteica:
            secciones["1_tarifas_oficiales_reteica_por_municipio"] = {
                "fuerza": "VINCULANTE · tabla oficial cargada por el contador",
                "uso": "Los municipios donde la empresa retiene ICA son exactamente estos, y la tarifa es la de la fila.",
                "filas": self.tarifas_reteica,
            }
        if self.criterios_contador:
            secciones["3_criterios_del_contador"] = {
                "fuerza": "ORIENTATIVO · criterio profesional documentado",
                "fuente": "Criterios registrados por el contador de esta empresa",
                "uso": "Guían la interpretación. No sustituyen una tarifa oficial ni el perfil fiscal.",
                "criterios": self.criterios_contador,
            }
        if self.casos_historicos:
            secciones["4_casos_contabilizados_similares"] = {
                "fuerza": "PRECEDENTE · NO es norma",
                "uso": (
                    "Causaciones de esta misma empresa que ya se contabilizaron en SIIGO. "
                    "Muestran cómo se resolvieron casos parecidos, pero NO determinan la "
                    "decisión actual: si contradicen una tarifa oficial o el perfil fiscal, "
                    "manda la tarifa o el perfil. Nunca justifiques una retención únicamente "
                    "por su frecuencia en estos casos."
                ),
                "casos": self.casos_historicos,
            }
        if self.conocimiento_conceptual:
            # Va numerado 5 —el último— a propósito: por debajo incluso de los precedentes.
            # Es doctrina que ayuda a leer las tablas, no un dato de esta empresa, y el
            # número es la señal más difícil de ignorar de que no puede desplazar a ninguna
            # de las anteriores.
            secciones["5_conocimiento_conceptual_reteica"] = self.conocimiento_conceptual
        return secciones


class RetentionEvidenceRetriever:
    """Recupera la evidencia de las cuatro fuentes y la consolida sin mezclarla."""

    def __init__(self, rag_client=None):
        self._rag = rag_client

    async def build(
        self,
        document: dict,
        tipos_candidatos: set[str],
        tarifas_retefuente: list[dict],
        tarifas_reteica: list[dict],
        criterios_contador: Optional[list[dict]] = None,
        municipios_reteica: Optional[set] = None,
    ) -> EvidenceBundle:
        """Arma el paquete de evidencia para un documento concreto.

        `tipos_candidatos` son los tipos de retención que sobrevivieron a los filtros previos
        (perfil fiscal y anclaje en tabla). Se usan para no traer criterios ni precedentes de
        retenciones que ya se descartaron.

        `criterios_contador` llega desde el integration-config-service: son datos del tenant,
        editables sin desplegar, y por eso no se leen de una constante de este servicio.
        """
        bundle = EvidenceBundle(
            tarifas_retefuente=tarifas_retefuente,
            tarifas_reteica=tarifas_reteica,
            criterios_contador=self._filtrar_criterios(criterios_contador, tipos_candidatos),
        )
        casos, traza = await self._casos_historicos(
            document, tipos_candidatos, municipios_reteica or set()
        )
        bundle.casos_historicos = casos
        bundle.traza_recuperacion = traza
        # Solo si ReteICA sigue en estudio. El corpus es específico de ese tributo, y cargarlo
        # en una factura donde la empresa no retiene ICA gastaría contexto en doctrina que no
        # puede cambiar ninguna decisión.
        if "reteica" in {t.strip().lower() for t in tipos_candidatos}:
            bundle.conocimiento_conceptual = reteica_knowledge.bloque_para_prompt(
                self._consulta(document, tipos_candidatos)
            )
        return bundle

    # ── Retriever 2: criterios del contador (datos del tenant) ────────────────

    @staticmethod
    def _filtrar_criterios(
        criterios: Optional[list[dict]], tipos_candidatos: set[str]
    ) -> list[dict]:
        """Deja los criterios del proceso general y los de las retenciones en estudio.

        Se filtra por tema para no gastar contexto en reglas de retenciones que ya se
        descartaron: si la empresa no es agente de ReteIVA, sus criterios no pintan nada en el
        prompt. Los de `proceso` entran siempre, porque gobiernan la decisión completa.
        """
        temas = {t.strip().lower() for t in tipos_candidatos} | {"proceso"}
        seleccion = []
        for c in criterios or []:
            if str(c.get("tema") or "").strip().lower() not in temas:
                continue
            seleccion.append(
                {
                    "tema": c.get("tema"),
                    "criterio": _sanitize(c.get("criterio")),
                    "responde_a": _sanitize(c.get("pregunta")),
                }
            )
        return seleccion

    # ── Retriever 4: casos contabilizados similares (búsqueda híbrida) ─────────

    async def _casos_historicos(
        self,
        document: dict,
        tipos_candidatos: set[str],
        municipios_reteica: Optional[set] = None,
    ) -> tuple[list[dict], dict]:
        """Precedentes contabilizados, buscados en dos pasadas de menor a mayor amplitud.

        **Pasada 1 — el mismo proveedor.** Es el precedente que de verdad vale: la retención
        depende del régimen y las responsabilidades del tercero, que son suyos y no cambian
        de factura a factura. Se filtra por NIT y se ordena por parecido del concepto.

        **Pasada 2 — el mismo concepto, otros proveedores.** Solo si la primera no encontró
        nada. Un proveedor nuevo no tiene historial propio, pero «mantenimiento locativo» se
        ha causado antes con otros terceros y esa imputación orienta. Se marca como tal, para
        que el modelo sepa que el precedente no es del mismo tercero y pondere en
        consecuencia.

        Todo es best-effort: sin RAG, o sin casos, la sugerencia sigue adelante con las
        reglas. Un sistema recién estrenado no tiene historial y debe funcionar igual.
        """
        traza: dict[str, Any] = {"estrategia": "ninguna", "encontrados": 0}
        if self._rag is None:
            return [], traza

        nit = _clean_nit(document.get("issuer_nit"))
        consulta = self._consulta(document, tipos_candidatos)

        # Pasada 1: mismo proveedor.
        if nit:
            casos = await self._buscar(consulta, {"issuer_nit": nit})
            if casos:
                traza = {
                    "estrategia": "mismo_proveedor",
                    "filtros": {"issuer_nit": nit},
                    "consulta": consulta,
                    "encontrados": len(casos),
                }
                return (
                    self._formatear(
                        casos, mismo_proveedor=True, municipios_reteica=municipios_reteica
                    ),
                    traza,
                )

        # Pasada 2: mismo concepto, cualquier proveedor.
        casos = await self._buscar(consulta, {})
        traza = {
            "estrategia": "concepto_similar_otros_proveedores" if casos else "sin_resultados",
            "filtros": {},
            "consulta": consulta,
            "encontrados": len(casos),
        }
        return (
            self._formatear(
                casos, mismo_proveedor=False, municipios_reteica=municipios_reteica
            ),
            traza,
        )

    async def _buscar(self, consulta: str, filtros: dict) -> list[dict]:
        try:
            return await self._rag.search(
                consulta,
                top_k=_TOP_K_CASOS,
                only_validated=True,  # RF-08: solo causaciones contabilizadas.
                filters=filtros,
            )
        except Exception as exc:  # noqa: BLE001
            # Se degrada a propósito —sin precedentes la sugerencia sigue con las reglas—,
            # pero con la traza completa. Este mismo `except` estuvo tapando durante meses un
            # error de programación: el cliente no aceptaba el filtro que se le pasaba, la
            # llamada moría en un TypeError y el sistema indexaba conocimiento que no
            # recuperaba nunca. Un mensaje de una línea no daba para verlo; un traceback sí.
            logger.warning(
                "RF-08: no se pudieron recuperar los casos históricos (filtros=%s): %s",
                filtros,
                exc,
                exc_info=True,
            )
            return []

    @staticmethod
    def _consulta(document: dict, tipos_candidatos: set[str]) -> str:
        """Texto con el que se busca el precedente.

        Antes era solo el nombre del emisor, que es justo lo que el filtro estructurado ya
        resuelve mejor. Aquí se usa lo que el embedding sí capta y el filtro no: **de qué
        trata la operación**. Las descripciones de las líneas son, según el contador, lo que
        determina el concepto tributario y también donde más errores se cometen.
        """
        partes: list[str] = []
        descripciones = [
            _sanitize(d.get("description"))
            for d in (document.get("details") or [])[:5]
            if d.get("description")
        ]
        if descripciones:
            partes.append("Conceptos facturados: " + "; ".join(descripciones))
        emisor = _sanitize(document.get("issuer_name"))
        if emisor:
            partes.append(f"Proveedor: {emisor}")
        if tipos_candidatos:
            partes.append("Retenciones en estudio: " + ", ".join(sorted(tipos_candidatos)))
        return " | ".join(partes) or "causación contabilizada"

    @staticmethod
    def _comparabilidad(
        municipio_caso: Any, mismo_proveedor: bool, municipios_reteica: Optional[set]
    ) -> dict:
        """Hasta qué punto el precedente es reutilizable para ESTA operación.

        No decide nada: describe. El modelo sigue siendo quien pondera, pero lo hace sobre un
        juicio ya calculado en vez de sobre dos códigos de municipio perdidos en un JSON.

        `municipio_comparable` es deliberadamente tri-estado. `null` significa «no consta»,
        que es el caso real cuando la empresa retiene en varios municipios: el indexador se
        niega a etiquetar el caso con uno de ellos antes que atribuirle el equivocado, y aquí
        se propaga esa misma abstención. Convertir «no consta» en `false` descartaría
        precedentes válidos; convertirlo en `true` es justamente el error que se quiere evitar.
        """
        codigo = str(municipio_caso or "").strip()
        municipios = {str(m).strip() for m in (municipios_reteica or set()) if str(m).strip()}
        municipio_comparable = None if not codigo or not municipios else codigo in municipios
        return {
            "mismo_proveedor": mismo_proveedor,
            "municipio_del_caso": codigo or None,
            "municipio_comparable": municipio_comparable,
            "verificar_antes_de_reutilizar": [
                "municipio / jurisdicción",
                "actividad económica o concepto de la operación",
                "tipo y régimen del tercero",
                "naturaleza de la operación",
                "tarifa vigente en la tabla de ReteICA",
            ],
        }

    @classmethod
    def _formatear(
        cls,
        casos: list[dict],
        mismo_proveedor: bool,
        municipios_reteica: Optional[set] = None,
    ) -> list[dict]:
        """Convierte los chunks en evidencia citable, con su procedencia explícita.

        Cada caso conserva el `siigo_id`: es lo que permite responder «¿de dónde salió esta
        sugerencia?» señalando un comprobante concreto de la contabilidad, y no un vago
        «el histórico».
        """
        formateados = []
        for caso in casos:
            metadata = caso.get("metadata") or {}
            formateados.append(
                {
                    "documento_id": caso.get("source_id"),
                    "comprobante_siigo": caso.get("siigo_id"),
                    "mismo_proveedor": mismo_proveedor,
                    "similitud": caso.get("similarity"),
                    "proveedor_nit": metadata.get("issuer_nit"),
                    "retenciones_practicadas": metadata.get("retention_types") or [],
                    "municipio": metadata.get("municipality_code"),
                    "causacion": _sanitize(caso.get("content"))[:_MAX_CASO_CHARS],
                    # RF-08 · comparabilidad. Un precedente solo informa si las condiciones
                    # son comparables, y para ReteICA la primera condición es la
                    # jurisdicción: la tarifa de un municipio no dice nada del de al lado.
                    # Se resuelve aquí, de forma determinística, en vez de confiar en que el
                    # modelo compare dos códigos DANE dentro de un JSON largo.
                    "comparabilidad": cls._comparabilidad(
                        metadata.get("municipality_code"),
                        mismo_proveedor,
                        municipios_reteica,
                    ),
                }
            )
        return formateados


def _sanitize(value: Any) -> str:
    """Neutraliza texto de terceros antes de incrustarlo en el prompt.

    El contenido de un caso histórico incluye descripciones que vinieron del XML de un
    proveedor. Aunque ya pasaron por la contabilización, siguen siendo texto ajeno: colapsar
    saltos y caracteres de control evita que un valor con formato malicioso simule
    instrucciones nuevas dentro del prompt.
    """
    if value is None:
        return ""
    return _CONTROL_CHARS.sub(" ", str(value)).strip()


def _clean_nit(nit: Optional[str]) -> str:
    """NIT sin dígito de verificación ni separadores, igual que al indexar.

    Debe coincidir con la normalización del xml-processor: si una parte guarda
    '900123456-7' y la otra busca '900123456', el historial del proveedor no se encuentra
    nunca y el sistema parece no haber aprendido nada.
    """
    if not nit:
        return ""
    limpio = str(nit).strip().replace(".", "").replace(" ", "")
    return limpio.split("-", 1)[0] if "-" in limpio else limpio
