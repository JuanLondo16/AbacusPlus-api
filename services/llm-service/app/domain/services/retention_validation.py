"""RF-08 · Capa determinística que valida lo que el modelo propone.

El prompt le dice al modelo cómo debe decidir; esto comprueba que lo hizo. La diferencia
importa: un prompt es una petición, y una petición no es una garantía. Todo lo que aquí se
verifica ya estaba escrito en las instrucciones del sistema —tomar la tarifa de la tabla,
respetar la base mínima, no retener a un autorretenedor—, y aun así hace falta comprobarlo
fuera del modelo, porque el coste de que se salte una de esas reglas no es una respuesta
peor: es dinero retenido de más a un tercero, en la contabilidad real de un cliente.

Cada regla de este módulo tiene una fuente concreta y ninguna es una interpretación nuestra:

- **La tarifa sale de la tabla oficial.** Lo exige el alcance del proyecto: «aplica el
  porcentaje definido en la tabla de impuestos para cada retención». El catálogo sincronizado
  desde SIIGO trae once ReteFuente que solo se distinguen por el porcentaje de su nombre, así
  que el modelo puede elegir una que no corresponda a ninguna tarifa vigente. Si el
  porcentaje del impuesto elegido no aparece en la tabla, la sugerencia no se puede sustentar
  y se descarta.
- **La base mínima.** Cada fila de las tablas trae su tope (`minimum_base_uvt` /
  `minimum_base_pesos`); por debajo no se practica la retención. Se compara contra el tope
  MÁS BAJO de las filas compatibles: rechazar solo cuando la base no alcanza ninguno de los
  topes posibles es el criterio conservador, el que nunca descarta una retención procedente.
- **Al autorretenedor no se le retiene en la fuente.** Es la respuesta literal del contador
  del cliente en el cuestionario de retenciones: «los de régimen común no le pueden hacer
  retención a un autorretenedor o gran contribuyente autorretenedor». El código O-15 del RUT
  identifica esa condición en la factura electrónica.
- **Sin IVA facturado no hay ReteIVA.** También del cuestionario: la primera condición para
  que proceda es «generar IVA». La base de la ReteIVA es el IVA de la factura, así que sin él
  la retención sería de cero.

Lo que este módulo NO hace es corregir. Una sugerencia que no supera una comprobación se
descarta y se explica por qué; nunca se sustituye por otra que el sistema considere más
adecuada. Elegir la tarifa correcta cuando la propuesta no cuadra exigiría saber el concepto
tributario de la operación, que es justamente lo que no se puede deducir sin criterio. Ante
la duda, RF-08 pide abstenerse y decirlo, no acertar por aproximación.
"""

import logging
from typing import Any, Optional

from app.domain.services.tax_catalog import (
    classify,
    is_practicable_on_purchase,
    motivo_no_practicable,
)

logger = logging.getLogger(__name__)

#: Código del RUT (lista 48 de la DIAN) que identifica a un autorretenedor.
_CODIGO_AUTORRETENEDOR = "O-15"

#: Margen al comparar porcentajes. Las tarifas viajan como `Numeric(10, 6)` en la base y como
#: `float` en el JSON, así que una igualdad estricta fallaría por el redondeo del formato, no
#: por una discrepancia real.
_TOLERANCIA_PCT = 1e-6


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tipo(valor: Any) -> str:
    return str(valor or "").strip().lower()


class RetentionValidator:
    """Comprueba cada sugerencia contra las fuentes vinculantes. No corrige: descarta.

    Se construye con lo que ya se recuperó para armar el prompt —las mismas tablas, el mismo
    perfil, el mismo documento—, de modo que valida contra exactamente la evidencia que el
    modelo tuvo delante y no contra una lectura posterior que podría haber cambiado.
    """

    def __init__(
        self,
        tarifas_retefuente: Optional[list[dict]] = None,
        tarifas_reteica: Optional[list[dict]] = None,
        uvt: Optional[int] = None,
        responsabilidades_emisor: Optional[list[dict]] = None,
        iva_documento: float = 0.0,
    ):
        self._fuente = tarifas_retefuente or []
        self._ica = tarifas_reteica or []
        self._uvt = uvt
        self._responsabilidades = responsabilidades_emisor or []
        self._iva = _num(iva_documento) or 0.0

    # ── API ────────────────────────────────────────────────────────────────────

    def rechazo(self, suggestion: dict) -> Optional[str]:
        """Motivo por el que la sugerencia no se sostiene, o None si es válida.

        El texto se le muestra al contador, así que nombra el dato que falló y no la regla
        interna: lo que necesita saber es qué revisar, no cómo está implementada la
        comprobación.
        """
        # La clase la fija la lectura del catálogo de Impuestos; solo se reclasifica aquí si
        # la sugerencia no la trae, para que el validador siga sirviendo a quien lo use suelto.
        tipo = _tipo(suggestion.get("clase")) or classify(suggestion)
        base = _num(suggestion.get("taxable_base")) or 0.0
        pct = _num(suggestion.get("percentage"))
        nombre = suggestion.get("name") or f"impuesto {suggestion.get('tax_id')}"

        if pct is None or pct <= 0:
            return f"«{nombre}» no tiene un porcentaje válido en el catálogo; no se sugirió."

        if not is_practicable_on_purchase(tipo):
            motivo = motivo_no_practicable(tipo)
            return (
                f"«{nombre}» no se sugirió: {motivo}."
                if motivo
                else (
                    f"«{nombre}» no se sugirió: no se reconoce como una retención "
                    "practicable al proveedor en una factura de compra."
                )
            )

        # La ReteIVA se comprueba antes que la base, y no después, porque cuando la factura
        # no trae IVA ambas cosas son ciertas a la vez —la base es cero *porque* no hay IVA— y
        # de las dos, la que el contador necesita leer es la causa y no el síntoma.
        if tipo == "reteiva":
            return self._rechazo_reteiva(nombre) or self._rechazo_por_base(nombre, base)

        if base <= 0:
            return self._rechazo_por_base(nombre, base)
        if tipo == "retefuente":
            return self._rechazo_retefuente(nombre, pct, base)
        return self._rechazo_reteica(nombre, pct, base)

    @staticmethod
    def _rechazo_por_base(nombre: str, base: float) -> Optional[str]:
        """Una retención sin base gravable no tiene valor que retener."""
        if base > 0:
            return None
        return (
            f"«{nombre}» no se sugirió: la base gravable calculada es cero, así que la "
            "retención no tendría valor."
        )

    # ── ReteFuente ─────────────────────────────────────────────────────────────

    def _rechazo_retefuente(self, nombre: str, pct: float, base: float) -> Optional[str]:
        if self._es_autorretenedor():
            return (
                f"«{nombre}» no se sugirió: el proveedor está marcado como autorretenedor "
                f"({_CODIGO_AUTORRETENEDOR}) en el RUT de la factura, y a un autorretenedor no "
                "se le practica retención en la fuente."
            )
        filas = [f for f in self._fuente if self._coincide(f.get("tarifa"), pct)]
        if not filas:
            return (
                f"«{nombre}» no se sugirió: su porcentaje ({pct:g}%) no corresponde a ninguna "
                "tarifa de la tabla de retención en la fuente cargada. Verifique la tabla o "
                "registre la retención manualmente."
            )
        return self._rechazo_por_base_minima(nombre, base, filas, "retención en la fuente")

    def _es_autorretenedor(self) -> bool:
        return any(
            str(r.get("codigo") or "").strip().upper() == _CODIGO_AUTORRETENEDOR
            for r in self._responsabilidades
        )

    # ── ReteICA ────────────────────────────────────────────────────────────────

    def _rechazo_reteica(self, nombre: str, pct: float, base: float) -> Optional[str]:
        filas = [f for f in self._ica if self._coincide(f.get("percentage"), pct)]
        if filas:
            return self._rechazo_por_base_minima(nombre, base, filas, "ReteICA")

        discrepancia = self._discrepancia_por_mil(pct)
        if discrepancia is not None:
            return (
                f"«{nombre}» no se sugirió: el catálogo de Impuestos trae {pct:g} y la tabla de "
                f"ReteICA trae {discrepancia:g} para el mismo municipio. Es la misma tarifa "
                "expresada en unidades distintas —por mil frente a porcentaje—, y aplicar una "
                "por la otra retendría diez veces de más o de menos. Unifique la unidad en las "
                "dos tablas antes de usar la sugerencia automática de ReteICA."
            )
        return (
            f"«{nombre}» no se sugirió: su porcentaje ({pct:g}%) no corresponde a ninguna "
            "tarifa de la tabla de ReteICA de los municipios donde la empresa retiene."
        )

    def _discrepancia_por_mil(self, pct: float) -> Optional[float]:
        """Detecta que catálogo y tabla expresan la misma tarifa en unidades distintas.

        El ICA se publica tradicionalmente **por mil**: la tarifa de servicios de Bogotá es
        9,66 por mil, es decir 0,966 %. El catálogo de Impuestos que sincroniza SIIGO trae
        «ReteICA 9.66» y la tabla de tarifas documenta guardar el porcentaje (0.966 => 0,966 %).
        Las dos cifras son correctas y describen lo mismo, pero no son la misma unidad.

        Sin esta comprobación, el desajuste se manifiesta como «esa tarifa no está en la tabla»,
        que es cierto pero inútil: el contador ve una tarifa idéntica en las dos pantallas y no
        entiende el rechazo. Peor sería lo contrario —dar por buena la del catálogo y calcular
        9,66 % sobre la base—, porque eso retiene diez veces de más sobre dinero de un tercero.

        No se corrige automáticamente. Cuál de las dos unidades es la correcta lo decide el
        contador, no este código: ambas convenciones existen y elegir por nuestra cuenta sería
        exactamente la clase de suposición que RF-08 prohíbe.
        """
        for fila in self._ica:
            valor = _num(fila.get("percentage"))
            if valor is None or valor <= 0:
                continue
            if self._coincide(valor * 10, pct) or self._coincide(valor / 10, pct):
                return valor
        return None

    # ── ReteIVA ────────────────────────────────────────────────────────────────

    def _rechazo_reteiva(self, nombre: str) -> Optional[str]:
        """La ReteIVA se practica sobre el IVA facturado; sin IVA no procede.

        No se comprueba contra ninguna tabla de tarifas porque no existe: la ReteIVA no
        depende del concepto ni del municipio, y su porcentaje sale del catálogo de impuestos
        igual que el de cualquier otra retención del documento.
        """
        if self._iva <= 0:
            return (
                f"«{nombre}» no se sugirió: la factura no tiene IVA, y la ReteIVA se practica "
                "sobre el IVA facturado."
            )
        return None

    # ── Comprobaciones compartidas ─────────────────────────────────────────────

    @staticmethod
    def _coincide(tarifa: Any, pct: float) -> bool:
        valor = _num(tarifa)
        return valor is not None and abs(valor - pct) <= _TOLERANCIA_PCT

    def _rechazo_por_base_minima(
        self, nombre: str, base: float, filas: list[dict], etiqueta: str
    ) -> Optional[str]:
        """Descarta la sugerencia solo si la base no alcanza NINGÚN tope de las filas compatibles.

        Varias filas pueden compartir tarifa con topes distintos —conceptos distintos del
        mismo municipio, o el mismo concepto para tipos de contribuyente distintos—. Cuál de
        ellas es la que corresponde depende del concepto tributario, que aquí no se conoce,
        así que se toma el tope más bajo: por debajo de él, la retención no procede bajo
        ninguna lectura posible, y ese es el único caso en que descartar es seguro.
        """
        topes = [t for t in (self._tope_en_pesos(f) for f in filas) if t is not None]
        if not topes:
            return None
        minimo = min(topes)
        if base >= minimo:
            return None
        return (
            f"«{nombre}» no se sugirió: la base gravable (${base:,.0f}) no alcanza la base "
            f"mínima de {etiqueta} (${minimo:,.0f}) de la tabla cargada."
        ).replace(",", ".")

    def _tope_en_pesos(self, fila: dict) -> Optional[float]:
        """Base mínima de una fila, en pesos, calculada desde la UVT siempre que se pueda.

        **Manda el importe que el contador cargó.** La tabla de tarifas es una fuente
        vinculante y se importa desde Excel precisamente para poder actualizarla sin
        desplegar: cuando cambia la UVT en enero, o cuando un decreto cambia las bases a
        mitad de año como el 572 de 2025, el contador vuelve a cargarla. Preferir una
        conversión calculada aquí sobre el importe que él escribió invertiría la jerarquía de
        fuentes que gobierna todo RF-08.

        La conversión desde UVT es el respaldo, para las filas —y las tablas enteras, como la
        de ReteICA— que solo traen el tope en UVT. Y la UVT que se usa tampoco es una
        constante del repositorio siempre que pueda evitarse: se deduce de la propia tabla
        importada (ver `_uvt_efectiva` en el caso de uso).

        Si no hay ninguna de las dos formas, no se compara nada: dejar pasar la sugerencia a
        la revisión del contador es preferible a descartarla con un tope inventado.
        """
        for clave in ("base_minima_pesos", "minimum_base_pesos"):
            valor = _num(fila.get(clave))
            if valor is not None:
                return valor
        for clave in ("base_minima_uvt", "minimum_base_uvt"):
            valor = _num(fila.get(clave))
            if valor is not None:
                return valor * self._uvt if self._uvt else None
        return None
