#!/usr/bin/env python3
"""RF-05 · Sonda de comportamiento de la API de SIIGO.

Responde con datos las preguntas que la documentación deja abiertas: si SIIGO tolera
peticiones simultáneas, dónde está su techo, qué códigos de error devuelve `/v1/purchases`
ante datos contables inválidos, cuánto tarda una factura en ser visible tras crearla, y si
la cabecera `Idempotency-Key` hace algo pese a no estar documentada para compras.

POR QUÉ NO SIRVE PROBAR ESTO DESDE LA INTERFAZ DE ABACUS
─────────────────────────────────────────────────────────
La cola de Abacus está para impedir exactamente las condiciones que aquí hay que provocar.
Con `ACCOUNTING_MAX_CONCURRENCY=1` los documentos salen uno detrás de otro, así que SIIGO
nunca vería dos peticiones a la vez y la prueba de concurrencia mediría la cola, no a SIIGO.
Por eso esta sonda habla **directamente** con `api.siigo.com`, sin pasar por Abacus.

ADVERTENCIA — ESTO CREA CONTABILIDAD REAL
──────────────────────────────────────────
Cada prueba que devuelve 201 crea una **factura de compra real** en la empresa contra la que
se ejecute. Úsese contra una **empresa de pruebas** de SIIGO. Si solo hay credenciales de
producción, ejecútense únicamente las pruebas marcadas como `--safe` (no crean nada) y
recábense credenciales de prueba antes de las demás.

El script lleva sus propias defensas: exige confirmación escrita para las pruebas que
escriben, registra todo lo creado en un fichero de rastro, y ofrece `--cleanup` para borrar
después lo que él mismo creó.

USO
───
    export SIIGO_USERNAME='...'
    export SIIGO_ACCESS_KEY='...'
    export SIIGO_PARTNER_ID='abacusplus'

    python3 siigo_probe.py --list                    # qué pruebas hay
    python3 siigo_probe.py --safe                    # solo lectura, no crea nada
    python3 siigo_probe.py --test t1                 # una prueba concreta
    python3 siigo_probe.py --test t3 --n 5           # concurrencia con 5 peticiones
    python3 siigo_probe.py --cleanup rastro.json     # borra lo creado

Los resultados se guardan en JSON. Ese fichero es el insumo para afinar la tabla de
clasificación de errores de Abacus (`domain/services/siigo_error_classifier.py`): cada
código nuevo que aparezca ahí es una fila que añadir.
"""

import argparse
import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

try:
    import httpx
except ImportError:
    sys.exit("Falta httpx.  pip install httpx")


BASE_URL = os.getenv("SIIGO_BASE_URL", "https://api.siigo.com")
RASTRO = "siigo_probe_creados.json"


# ── Autenticación ──────────────────────────────────────────────────────────────


def autenticar() -> dict:
    """Obtiene el token y devuelve las cabeceras listas para usar."""
    usuario = os.getenv("SIIGO_USERNAME")
    clave = os.getenv("SIIGO_ACCESS_KEY")
    partner = os.getenv("SIIGO_PARTNER_ID", "abacusplus")

    if not usuario or not clave:
        sys.exit("Faltan SIIGO_USERNAME y/o SIIGO_ACCESS_KEY en el entorno.")

    r = httpx.post(
        f"{BASE_URL}/auth/access-token",
        json={"username": usuario, "access_key": clave},
        headers={"Content-Type": "application/json", "Partner-Id": partner},
        timeout=30,
    )
    r.raise_for_status()
    token = r.json()["access_token"]

    print(f"  Autenticado como {usuario}")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Partner-Id": partner,
    }


# ── Registro de lo creado, para poder deshacerlo ───────────────────────────────


def anotar_creado(siigo_id: str, prueba: str) -> None:
    """Deja constancia de cada factura creada.

    Se escribe en disco inmediatamente después de cada creación, no al final: si el script
    se interrumpe a mitad de una prueba de concurrencia, lo ya creado tiene que quedar
    registrado igualmente. Un rastro incompleto es justo lo que obliga a buscar a mano en
    SIIGO qué se creó y qué no.
    """
    registro = []
    if os.path.exists(RASTRO):
        with open(RASTRO) as f:
            registro = json.load(f)
    registro.append(
        {"siigo_id": siigo_id, "prueba": prueba, "creado_en": _ahora()}
    )
    with open(RASTRO, "w") as f:
        json.dump(registro, f, indent=2)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Cuerpo de una factura de compra ────────────────────────────────────────────


def payload_valido(parametros: dict, sufijo: str = "") -> dict:
    """Una factura de compra mínima y válida.

    Los identificadores de catálogo (`document_id`, `payment_id`, la cuenta, el NIT del
    proveedor) NO se inventan: se leen de la configuración que se le pasa al script, porque
    son distintos en cada empresa de SIIGO. Ver `--config` en la ayuda.
    """
    return {
        "document": {"id": parametros["document_id"]},
        "date": parametros.get("fecha") or date.today().isoformat(),
        "supplier": {
            "identification": parametros["supplier_identification"],
            "branch_office": parametros.get("supplier_branch_office", 0),
        },
        "provider_invoice": {
            "prefix": parametros.get("prefix", "TEST"),
            # Número único por petición: sin él, SIIGO podría rechazar por duplicado y
            # estaríamos midiendo esa validación en vez de lo que queremos medir.
            "number": f"{parametros.get('numero_base', 'PROBE')}{sufijo}",
        },
        "items": [
            {
                "type": "Account",
                "code": parametros["account_code"],
                "quantity": 1,
                "price": parametros.get("price", 1000),
            }
        ],
        "payments": [
            {"id": parametros["payment_id"], "value": parametros.get("price", 1000)}
        ],
    }


def enviar(headers: dict, cuerpo: dict, extra_headers=None, timeout=130) -> dict:
    """Una petición a POST /v1/purchases, conservando todo lo observable."""
    h = dict(headers)
    if extra_headers:
        h.update(extra_headers)

    inicio = time.monotonic()
    try:
        r = httpx.post(
            f"{BASE_URL}/v1/purchases", json=cuerpo, headers=h, timeout=timeout
        )
        duracion = time.monotonic() - inicio
        try:
            respuesta = r.json()
        except Exception:  # noqa: BLE001
            respuesta = {"_texto": r.text[:1000]}
        return {
            "http": r.status_code,
            "duracion_s": round(duracion, 3),
            "respuesta": respuesta,
            "siigo_id": respuesta.get("id") if isinstance(respuesta, dict) else None,
            "codigos": _codigos(respuesta),
            "headers_respuesta": {
                k: v for k, v in r.headers.items()
                # Interesan las cabeceras que puedan revelar política de cupo: si SIIGO
                # publica un Retry-After o un contador de peticiones restantes, el limitador
                # de Abacus podría respetarlo en vez de estimarlo.
                if k.lower().startswith(("retry", "x-rate", "ratelimit", "x-ratelimit"))
            },
        }
    except httpx.TimeoutException:
        return {
            "http": None,
            "duracion_s": round(time.monotonic() - inicio, 3),
            "error": "TIMEOUT",
            "nota": "La factura PUDO haberse creado. Verificar antes de concluir.",
        }
    except httpx.HTTPError as exc:
        return {
            "http": None,
            "duracion_s": round(time.monotonic() - inicio, 3),
            "error": f"RED: {exc}",
            "nota": "La factura PUDO haberse creado. Verificar antes de concluir.",
        }


def _codigos(respuesta) -> list:
    """Extrae los `Code` del cuerpo de error de SIIGO."""
    if not isinstance(respuesta, dict):
        return []
    errores = respuesta.get("Errors") or respuesta.get("errors") or []
    if isinstance(errores, list):
        return [e.get("Code") for e in errores if isinstance(e, dict) and e.get("Code")]
    return []


# ── Pruebas ────────────────────────────────────────────────────────────────────


def t1_individual(headers, cfg):
    """T1 · Una sola petición. Establece la línea base: ¿es síncrono? ¿cuánto tarda?"""
    res = enviar(headers, payload_valido(cfg, sufijo=uuid.uuid4().hex[:6]))
    if res.get("siigo_id"):
        anotar_creado(res["siigo_id"], "t1")
    return {
        "prueba": "T1 · petición individual",
        "responde_con_id": bool(res.get("siigo_id")),
        "sincrono": bool(res.get("siigo_id")),
        "resultado": res,
    }


def t3_concurrencia(headers, cfg, n: int):
    """T3 · N peticiones **realmente simultáneas**.

    Todas se lanzan a la vez con un pool de hilos. Es la diferencia con enviarlas desde
    Abacus: aquí no hay cola que las serialice.
    """
    cuerpos = [payload_valido(cfg, sufijo=f"C{n}X{i}{uuid.uuid4().hex[:4]}") for i in range(n)]

    arranque = time.monotonic()
    with ThreadPoolExecutor(max_workers=n) as pool:
        resultados = list(pool.map(lambda c: enviar(headers, c), cuerpos))
    total = time.monotonic() - arranque

    for r in resultados:
        if r.get("siigo_id"):
            anotar_creado(r["siigo_id"], f"t3-n{n}")

    exitos = [r for r in resultados if r.get("http") in (200, 201)]
    duraciones = [r["duracion_s"] for r in resultados if r.get("duracion_s")]

    return {
        "prueba": f"T3 · {n} peticiones simultáneas",
        "n": n,
        "exitos": len(exitos),
        "fallos": n - len(exitos),
        "codigos_http": sorted({r.get("http") for r in resultados}, key=lambda x: (x is None, x)),
        "duracion_total_s": round(total, 3),
        "latencia_min_s": round(min(duraciones), 3) if duraciones else None,
        "latencia_max_s": round(max(duraciones), 3) if duraciones else None,
        # La pregunta que decide si hay concurrencia real: si SIIGO las procesa en paralelo,
        # el total se parece a la latencia máxima. Si las serializa, se parece a la suma.
        "latencia_suma_s": round(sum(duraciones), 3) if duraciones else None,
        "veredicto": _veredicto_concurrencia(total, duraciones),
        "resultados": resultados,
    }


def _veredicto_concurrencia(total: float, duraciones: list) -> str:
    if not duraciones:
        return "sin datos"
    suma = sum(duraciones)
    maximo = max(duraciones)
    if total <= maximo * 1.3:
        return "PARALELO — SIIGO atendió las peticiones a la vez"
    if total >= suma * 0.8:
        return "SERIALIZADO — SIIGO las atendió una tras otra"
    return "PARCIAL — revisar latencias individuales"


def t4_rate_limit(headers, cfg, n: int):
    """T4 · Superar el cupo a propósito, para ver cómo lo comunica SIIGO.

    Interesa sobre todo si la respuesta trae `Retry-After` o algún contador: si lo trae, el
    limitador de Abacus puede respetarlo en lugar de estimar la espera.
    """
    resultados = []
    for i in range(n):
        r = enviar(headers, payload_valido(cfg, sufijo=f"RL{i}{uuid.uuid4().hex[:4]}"))
        if r.get("siigo_id"):
            anotar_creado(r["siigo_id"], "t4")
        resultados.append(r)
        if r.get("http") == 429:
            print(f"    429 en la petición {i + 1}")
            break

    limitadas = [r for r in resultados if r.get("http") == 429]
    return {
        "prueba": f"T4 · rate limit ({n} peticiones seguidas)",
        "peticiones_hasta_429": len(resultados) if limitadas else None,
        "hubo_429": bool(limitadas),
        "cabeceras_de_cupo": [r.get("headers_respuesta") for r in limitadas] or None,
        "codigos": limitadas[0].get("codigos") if limitadas else None,
        "resultados": resultados,
    }


def t5_consulta(headers, cfg):
    """T5 · ¿Se puede filtrar `GET /v1/purchases` por el número de factura del proveedor?

    No crea nada. Si el filtro existe, la reconciliación de Abacus pasa de un barrido por
    fechas a una consulta exacta.
    """
    pruebas = {}
    hoy = date.today().isoformat()

    for nombre, params in {
        "por_fecha": {"created_start": hoy, "created_end": hoy},
        "por_numero_proveedor": {"provider_invoice_number": cfg.get("numero_base", "PROBE")},
        "por_numero": {"number": cfg.get("numero_base", "PROBE")},
        "por_nombre": {"name": cfg.get("numero_base", "PROBE")},
    }.items():
        try:
            r = httpx.get(
                f"{BASE_URL}/v1/purchases", params=params, headers=headers, timeout=60
            )
            cuerpo = r.json() if r.status_code == 200 else {"_texto": r.text[:400]}
            pruebas[nombre] = {
                "http": r.status_code,
                "params": params,
                "resultados": (
                    len(cuerpo.get("results", [])) if isinstance(cuerpo, dict) else None
                ),
                "muestra": str(cuerpo)[:400],
            }
        except httpx.HTTPError as exc:
            pruebas[nombre] = {"error": str(exc)}

    return {"prueba": "T5 · filtros de consulta", "filtros": pruebas}


def t6_indexacion(headers, cfg):
    """T6 · Latencia de indexación. **La prueba más importante para no duplicar.**

    Crea una factura y la busca a intervalos crecientes. Si tarda en aparecer, una
    reconciliación demasiado pronta devolvería «no existe» sobre una factura que sí se creó,
    y ese falso negativo autorizaría un reenvío duplicado.

    El resultado fija `ACCOUNTING_RECONCILE_DELAY_SECONDS`.
    """
    numero = f"IDX{uuid.uuid4().hex[:8]}"
    creado = enviar(headers, payload_valido(cfg, sufijo=numero))
    if not creado.get("siigo_id"):
        return {"prueba": "T6 · latencia de indexación", "error": "No se pudo crear", "detalle": creado}

    anotar_creado(creado["siigo_id"], "t6")
    hoy = date.today().isoformat()
    observaciones = []

    for espera in (1, 2, 5, 10, 30, 60):
        time.sleep(espera if not observaciones else espera - observaciones[-1]["t_s"])
        r = httpx.get(
            f"{BASE_URL}/v1/purchases",
            params={"created_start": hoy, "created_end": hoy, "page_size": 100},
            headers=headers,
            timeout=60,
        )
        encontrada = False
        if r.status_code == 200:
            cuerpo = r.json()
            encontrada = any(
                x.get("id") == creado["siigo_id"] for x in cuerpo.get("results", [])
            )
        observaciones.append({"t_s": espera, "visible": encontrada, "http": r.status_code})
        print(f"    t+{espera}s → {'visible' if encontrada else 'todavía no'}")
        if encontrada:
            break

    visible = next((o for o in observaciones if o["visible"]), None)
    return {
        "prueba": "T6 · latencia de indexación",
        "siigo_id": creado["siigo_id"],
        "visible_desde_s": visible["t_s"] if visible else "no visible en 60 s",
        "observaciones": observaciones,
    }


def t7_idempotency(headers, cfg):
    """T7 · ¿Hace algo `Idempotency-Key` en `/v1/purchases` pese a no estar documentado?

    Envía dos veces el MISMO cuerpo con la MISMA clave. Tres desenlaces posibles:
      · dos identificadores distintos → la cabecera se ignora (lo esperado)
      · el mismo identificador dos veces → **funciona**, y cambia toda la estrategia
      · un error → la rechaza explícitamente

    Si sale el segundo caso, hay que replantear el diseño: buena parte de la complejidad de
    RF-05 existe porque se asume el primero.
    """
    clave = uuid.uuid4().hex[:30]
    cuerpo = payload_valido(cfg, sufijo=f"IDEM{uuid.uuid4().hex[:6]}")

    primero = enviar(headers, cuerpo, extra_headers={"Idempotency-Key": clave})
    if primero.get("siigo_id"):
        anotar_creado(primero["siigo_id"], "t7-1")

    time.sleep(2)
    segundo = enviar(headers, cuerpo, extra_headers={"Idempotency-Key": clave})
    if segundo.get("siigo_id"):
        anotar_creado(segundo["siigo_id"], "t7-2")

    id1, id2 = primero.get("siigo_id"), segundo.get("siigo_id")
    if id1 and id2 and id1 == id2:
        veredicto = "FUNCIONA — misma clave, mismo comprobante. REPLANTEAR EL DISEÑO."
    elif id1 and id2:
        veredicto = "SE IGNORA — se crearon DOS facturas. Confirma lo asumido."
    else:
        veredicto = "RECHAZA o falló — revisar el detalle."

    return {
        "prueba": "T7 · Idempotency-Key en compras",
        "clave": clave,
        "veredicto": veredicto,
        "id_primero": id1,
        "id_segundo": id2,
        "primero": primero,
        "segundo": segundo,
    }


def t8_duplicado(headers, cfg):
    """T8 · Mismo número de factura de proveedor, dos veces, SIN clave de idempotencia.

    ¿Devuelve `duplicated_document` o crea el duplicado en silencio? De la respuesta depende
    si Abacus puede apoyarse en esa validación o si toda la defensa es suya.
    """
    numero = f"DUP{uuid.uuid4().hex[:8]}"
    cuerpo = payload_valido(cfg, sufijo=numero)

    primero = enviar(headers, cuerpo)
    if primero.get("siigo_id"):
        anotar_creado(primero["siigo_id"], "t8-1")

    time.sleep(2)
    segundo = enviar(headers, cuerpo)
    if segundo.get("siigo_id"):
        anotar_creado(segundo["siigo_id"], "t8-2")

    if segundo.get("siigo_id"):
        veredicto = "CREA EL DUPLICADO — SIIGO no valida el número de proveedor."
    else:
        veredicto = f"LO RECHAZA — códigos: {segundo.get('codigos')}"

    return {
        "prueba": "T8 · número de proveedor repetido",
        "numero": numero,
        "veredicto": veredicto,
        "primero": primero,
        "segundo": segundo,
    }


def t9_errores(headers, cfg):
    """T9 · El catálogo REAL de errores de /v1/purchases. La prueba de más valor.

    Provoca cada fallo a propósito y anota el `Code` exacto que devuelve SIIGO. Cada código
    que aparezca aquí es una fila que añadir a la tabla de clasificación de Abacus, y con
    ella un mensaje mucho mejor para el contador que el que da el respaldo por HTTP status.

    Ninguno de estos casos debería crear nada: son rechazos de validación. Si alguno
    devolviera 201, esa sola observación ya sería un hallazgo.
    """
    casos = {
        "cuenta_puc_inexistente": {"account_code": "9999999999"},
        "cuenta_puc_inactiva": {"account_code": cfg.get("cuenta_inactiva", "9999999998")},
        "tercero_inexistente": {"supplier_identification": "999999999"},
        "centro_costo_inexistente": {"_cost_center": 999999},
        "impuesto_inexistente": {"_tax_id": 999999},
        "retencion_inexistente": {"_retention_id": 999999},
        "forma_pago_inexistente": {"payment_id": 999999},
        "tipo_comprobante_inexistente": {"document_id": 999999},
        "fecha_fuera_de_periodo": {"fecha": "2019-01-01"},
        "cantidad_cero": {"_quantity": 0},
        "pago_descuadrado": {"_payment_value": 1},
        "sin_items": {"_sin_items": True},
    }

    hallazgos = {}
    for nombre, mutacion in casos.items():
        c = dict(cfg)
        c.update({k: v for k, v in mutacion.items() if not k.startswith("_")})
        cuerpo = payload_valido(c, sufijo=f"E{uuid.uuid4().hex[:6]}")

        # Mutaciones que tocan la estructura del cuerpo, no la configuración.
        if mutacion.get("_cost_center"):
            cuerpo["cost_center"] = mutacion["_cost_center"]
        if mutacion.get("_tax_id"):
            cuerpo["items"][0]["taxes"] = [{"id": mutacion["_tax_id"]}]
        if mutacion.get("_retention_id"):
            cuerpo["retentions"] = [mutacion["_retention_id"]]
        if mutacion.get("_quantity") is not None:
            cuerpo["items"][0]["quantity"] = mutacion["_quantity"]
        if mutacion.get("_payment_value"):
            cuerpo["payments"][0]["value"] = mutacion["_payment_value"]
        if mutacion.get("_sin_items"):
            cuerpo["items"] = []

        res = enviar(headers, cuerpo, timeout=60)
        if res.get("siigo_id"):
            # No debería ocurrir en una prueba de validación. Se anota igualmente.
            anotar_creado(res["siigo_id"], f"t9-{nombre}")

        hallazgos[nombre] = {
            "http": res.get("http"),
            "codigos": res.get("codigos"),
            "mensaje": _mensaje(res.get("respuesta")),
            "creo_algo": bool(res.get("siigo_id")),
        }
        print(f"    {nombre:32} → {res.get('http')}  {res.get('codigos')}")
        # Se espacian para no chocar con el cupo, que en empresa de pruebas es de 10/min.
        time.sleep(7)

    return {"prueba": "T9 · catálogo real de errores", "casos": hallazgos}


def _mensaje(respuesta) -> str:
    if not isinstance(respuesta, dict):
        return ""
    errores = respuesta.get("Errors") or respuesta.get("errors") or []
    if isinstance(errores, list) and errores:
        return "; ".join(str(e.get("Message", "")) for e in errores if isinstance(e, dict))[:300]
    return str(respuesta)[:300]


def t11_timeout(headers, cfg):
    """T11 · Cortar a propósito y comprobar si la factura se creó igualmente.

    Reproduce el escenario que justifica el cerrojo entero: se corta a los 2 segundos, muy
    por debajo de lo que SIIGO tarda, y después se busca. Si aparece, queda demostrado que un
    timeout **no** significa que no se creó — que es exactamente lo que Abacus asume.
    """
    numero = f"TMO{uuid.uuid4().hex[:8]}"
    cuerpo = payload_valido(cfg, sufijo=numero)

    print("    Enviando con timeout de 2 s (se espera que corte)…")
    corte = enviar(headers, cuerpo, timeout=2)

    print("    Esperando 30 s antes de verificar…")
    time.sleep(30)

    hoy = date.today().isoformat()
    r = httpx.get(
        f"{BASE_URL}/v1/purchases",
        params={"created_start": hoy, "created_end": hoy, "page_size": 100},
        headers=headers,
        timeout=60,
    )
    encontrada = None
    if r.status_code == 200:
        for x in r.json().get("results", []):
            factura = x.get("provider_invoice") or {}
            if numero in str(factura.get("number", "")):
                encontrada = x.get("id")
                break

    if encontrada:
        anotar_creado(encontrada, "t11")

    return {
        "prueba": "T11 · timeout y verificación posterior",
        "corte": corte,
        "se_creo_pese_al_timeout": bool(encontrada),
        "siigo_id": encontrada,
        "veredicto": (
            "CONFIRMADO: un timeout NO significa que no se creó. El cerrojo está justificado."
            if encontrada
            else "En este intento no se creó. No demuestra lo contrario: repetir varias veces."
        ),
    }


# ── Limpieza ───────────────────────────────────────────────────────────────────


def limpiar(headers, fichero: str):
    """Borra en SIIGO las facturas que este script creó.

    Solo toca lo que consta en el fichero de rastro: nunca busca ni borra por criterio, para
    que un error aquí no pueda alcanzar contabilidad que no sea de la prueba.
    """
    if not os.path.exists(fichero):
        sys.exit(f"No existe el fichero de rastro {fichero}")

    with open(fichero) as f:
        registro = json.load(f)

    pendientes = [r for r in registro if not r.get("borrado")]
    if not pendientes:
        print("  No hay nada pendiente de borrar.")
        return

    print(f"  Se van a BORRAR {len(pendientes)} facturas de SIIGO.")
    if input("  Escriba BORRAR para confirmar: ").strip() != "BORRAR":
        sys.exit("  Cancelado.")

    for r in pendientes:
        try:
            resp = httpx.delete(
                f"{BASE_URL}/v1/purchases/{r['siigo_id']}", headers=headers, timeout=60
            )
            r["borrado"] = resp.status_code in (200, 204)
            r["http_borrado"] = resp.status_code
            print(f"    {r['siigo_id']} → {resp.status_code}")
        except httpx.HTTPError as exc:
            r["error_borrado"] = str(exc)
            print(f"    {r['siigo_id']} → error: {exc}")
        time.sleep(1)

    with open(fichero, "w") as f:
        json.dump(registro, f, indent=2)

    fallidos = [r for r in registro if not r.get("borrado")]
    if fallidos:
        print(f"\n  ⚠ Quedan {len(fallidos)} sin borrar. Anúlelas manualmente en SIIGO:")
        for r in fallidos:
            print(f"      {r['siigo_id']}  ({r['prueba']})")


# ── Entrada ────────────────────────────────────────────────────────────────────

PRUEBAS = {
    "t1": ("Petición individual — línea base", t1_individual, True),
    "t3": ("N peticiones simultáneas — concurrencia", None, True),
    "t4": ("Rate limit — superar el cupo", None, True),
    "t5": ("Filtros de GET /v1/purchases", t5_consulta, False),
    "t6": ("Latencia de indexación", t6_indexacion, True),
    "t7": ("Idempotency-Key en compras", t7_idempotency, True),
    "t8": ("Número de proveedor repetido", t8_duplicado, True),
    "t9": ("Catálogo real de errores", t9_errores, True),
    "t11": ("Timeout y verificación posterior", t11_timeout, True),
}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="lista las pruebas disponibles")
    p.add_argument("--test", help="ejecuta una prueba concreta (t1, t3, …)")
    p.add_argument("--safe", action="store_true", help="solo las pruebas que NO crean nada")
    p.add_argument("--n", type=int, default=5, help="nº de peticiones para t3 y t4")
    p.add_argument("--config", default="siigo_probe_config.json", help="identificadores de catálogo")
    p.add_argument("--out", default="siigo_probe_resultados.json", help="fichero de salida")
    p.add_argument("--cleanup", help="borra lo creado, según el fichero de rastro")
    args = p.parse_args()

    if args.list:
        print("\nPruebas disponibles:\n")
        for clave, (desc, _, escribe) in PRUEBAS.items():
            marca = "CREA FACTURAS" if escribe else "solo lectura"
            print(f"  {clave:5} {desc:45} [{marca}]")
        print(f"\nBase: {BASE_URL}\n")
        return

    headers = autenticar()

    if args.cleanup:
        limpiar(headers, args.cleanup)
        return

    if not os.path.exists(args.config):
        sys.exit(
            f"\nFalta {args.config}. Cree el fichero con los identificadores de catálogo de\n"
            "la empresa contra la que se va a probar. Ejemplo:\n\n"
            + json.dumps(
                {
                    "document_id": 19693,
                    "payment_id": 5636,
                    "account_code": "51952501",
                    "supplier_identification": "900276962",
                    "supplier_branch_office": 0,
                    "price": 1000,
                    "prefix": "TEST",
                    "numero_base": "PROBE",
                },
                indent=2,
            )
            + "\n\nEstos valores son distintos en cada empresa de SIIGO: no se inventan.\n"
        )

    with open(args.config) as f:
        cfg = json.load(f)

    seleccion = [args.test] if args.test else list(PRUEBAS)
    if args.safe:
        seleccion = [k for k in seleccion if not PRUEBAS[k][2]]

    escriben = [k for k in seleccion if PRUEBAS[k][2]]
    if escriben:
        print(f"\n  ⚠ ADVERTENCIA — {', '.join(escriben)} CREAN FACTURAS DE COMPRA REALES")
        print(f"     en la empresa de {BASE_URL}.")
        print("     Ejecútese contra una EMPRESA DE PRUEBAS de SIIGO.\n")
        if input("  Escriba EJECUTAR para continuar: ").strip() != "EJECUTAR":
            sys.exit("  Cancelado.")

    resultados = {"base_url": BASE_URL, "inicio": _ahora(), "pruebas": []}

    for clave in seleccion:
        desc, fn, _ = PRUEBAS[clave]
        print(f"\n── {clave.upper()} · {desc}")
        try:
            if clave == "t3":
                r = t3_concurrencia(headers, cfg, args.n)
            elif clave == "t4":
                r = t4_rate_limit(headers, cfg, args.n)
            else:
                r = fn(headers, cfg)
        except Exception as exc:  # noqa: BLE001
            r = {"prueba": clave, "error_del_script": str(exc)}
        resultados["pruebas"].append(r)
        print(f"   {json.dumps({k: v for k, v in r.items() if k not in ('resultados', 'casos')}, ensure_ascii=False)[:300]}")

    resultados["fin"] = _ahora()
    with open(args.out, "w") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)

    print(f"\n  Resultados en {args.out}")
    if os.path.exists(RASTRO):
        with open(RASTRO) as f:
            n = len([r for r in json.load(f) if not r.get("borrado")])
        if n:
            print(f"  ⚠ Se crearon {n} facturas. Bórrelas con:")
            print(f"      python3 {sys.argv[0]} --cleanup {RASTRO}")


if __name__ == "__main__":
    main()
