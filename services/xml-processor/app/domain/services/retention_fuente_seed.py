"""Tabla estándar de Retención en la Fuente (ReteFuente) — Colombia 2026.

Fuente: tabla pública de tarifas por concepto (UVT 2026 = $52.374, Resolución DIAN 000238 del
15 de diciembre de 2025). Son tarifas NACIONALES, iguales para todos los tenants, por eso se
declaran como semilla reutilizable y se cargan en `retention_fuente_rates` de cada tenant vía
el endpoint interno de seed.

QUÉ CAMBIA CADA AÑO Y QUÉ NO. Las **tarifas** (los porcentajes) no se actualizan por el
cambio de año: las fija el Estatuto Tributario y solo cambian cuando lo hace un decreto, que
puede ocurrir en cualquier momento —en 2026 pasó a mitad de año, al levantarse la suspensión
del Decreto 572 de 2025, vigente de nuevo desde el 1 de julio de 2026—. Lo que sí cambia cada
enero es la **UVT**, y con ella el equivalente en pesos de las bases mínimas. Las bases en UVT
tampoco cambian por el año.

Consecuencia práctica: `minimum_base_pesos` envejece cada enero y `minimum_base_uvt` no. Por
eso la validación de RF-08 recalcula el tope desde la UVT del año del documento y usa el
importe guardado solo como respaldo (`llm-service · domain/services/retention_validation.py`).

IMPORTANTE (para el contador): esta tabla es un punto de partida tomado de una fuente
secundaria y debe validarse. Casos a confirmar: honorarios de personas naturales (10% vs 11%
según supere 3.300 UVT/año) y bases mínimas de conceptos específicos. Las tarifas se guardan
como porcentaje (2.5 = 2.5%). `taxpayer_type`: 'declarante' | 'no_declarante' | 'todos' |
'personas_juridicas' | 'personas_naturales'.
"""

UVT_2026 = 52374

# (concepto, taxpayer_type, base_uvt, base_pesos, tarifa_%)
STANDARD_RETEFUENTE_2026: list[dict] = [
    {"retention_concept": "Compras generales", "taxpayer_type": "declarante", "minimum_base_uvt": 10, "minimum_base_pesos": 523740, "rate_percentage": 2.5},
    {"retention_concept": "Compras generales", "taxpayer_type": "no_declarante", "minimum_base_uvt": 10, "minimum_base_pesos": 523740, "rate_percentage": 3.5},
    {"retention_concept": "Compras con tarjeta débito o crédito", "taxpayer_type": "todos", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 1.5},
    {"retention_concept": "Compras de bienes o productos agrícolas sin procesamiento industrial", "taxpayer_type": "todos", "minimum_base_uvt": 70, "minimum_base_pesos": 3666180, "rate_percentage": 1.5},
    {"retention_concept": "Compras de café pergamino o cereza", "taxpayer_type": "todos", "minimum_base_uvt": 70, "minimum_base_pesos": 3666180, "rate_percentage": 0.5},
    {"retention_concept": "Compras de combustibles derivados del petróleo", "taxpayer_type": "todos", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 0.1},
    {"retention_concept": "Enajenación de activos fijos de personas naturales", "taxpayer_type": "personas_naturales", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 1.0},
    {"retention_concept": "Compra de bienes raíces para vivienda (hasta 20.000 UVT)", "taxpayer_type": "todos", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 1.0},
    {"retention_concept": "Compra de bienes raíces para uso distinto a vivienda", "taxpayer_type": "todos", "minimum_base_uvt": 10, "minimum_base_pesos": 523740, "rate_percentage": 2.5},
    {"retention_concept": "Servicios generales", "taxpayer_type": "declarante", "minimum_base_uvt": 2, "minimum_base_pesos": 104748, "rate_percentage": 4.0},
    {"retention_concept": "Servicios generales", "taxpayer_type": "no_declarante", "minimum_base_uvt": 2, "minimum_base_pesos": 104748, "rate_percentage": 6.0},
    {"retention_concept": "Servicios de transporte de carga", "taxpayer_type": "todos", "minimum_base_uvt": 4, "minimum_base_pesos": 209496, "rate_percentage": 1.0},
    {"retention_concept": "Servicio de transporte nacional de pasajeros (terrestre)", "taxpayer_type": "todos", "minimum_base_uvt": 27, "minimum_base_pesos": 1414098, "rate_percentage": 3.5},
    {"retention_concept": "Servicio de transporte nacional de pasajeros (aéreo o marítimo)", "taxpayer_type": "todos", "minimum_base_uvt": 4, "minimum_base_pesos": 209496, "rate_percentage": 1.0},
    {"retention_concept": "Servicios prestados por empresas temporales de empleo (sobre AIU)", "taxpayer_type": "todos", "minimum_base_uvt": 4, "minimum_base_pesos": 209496, "rate_percentage": 1.0},
    {"retention_concept": "Servicios de vigilancia y aseo (sobre AIU)", "taxpayer_type": "todos", "minimum_base_uvt": 4, "minimum_base_pesos": 209496, "rate_percentage": 2.0},
    {"retention_concept": "Servicios integrales de salud (IPS)", "taxpayer_type": "todos", "minimum_base_uvt": 4, "minimum_base_pesos": 209496, "rate_percentage": 2.0},
    {"retention_concept": "Servicios de hoteles y restaurantes", "taxpayer_type": "todos", "minimum_base_uvt": 4, "minimum_base_pesos": 209496, "rate_percentage": 3.5},
    {"retention_concept": "Arrendamiento de bienes muebles", "taxpayer_type": "todos", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 4.0},
    {"retention_concept": "Arrendamiento de bienes inmuebles", "taxpayer_type": "todos", "minimum_base_uvt": 27, "minimum_base_pesos": 1414098, "rate_percentage": 3.5},
    {"retention_concept": "Otros ingresos tributarios", "taxpayer_type": "declarante", "minimum_base_uvt": 27, "minimum_base_pesos": 1414098, "rate_percentage": 2.5},
    {"retention_concept": "Otros ingresos tributarios", "taxpayer_type": "no_declarante", "minimum_base_uvt": 27, "minimum_base_pesos": 1414098, "rate_percentage": 3.5},
    {"retention_concept": "Honorarios y comisiones", "taxpayer_type": "personas_juridicas", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 11.0},
    {"retention_concept": "Honorarios y comisiones (personas naturales, contratos > 3.300 UVT)", "taxpayer_type": "personas_naturales", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 11.0},
    {"retention_concept": "Honorarios y comisiones (personas naturales, contratos <= 3.300 UVT)", "taxpayer_type": "personas_naturales", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 10.0},
    {"retention_concept": "Licenciamiento o derecho de uso de software", "taxpayer_type": "todos", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 3.5},
    {"retention_concept": "Rendimientos financieros en general", "taxpayer_type": "todos", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 7.0},
    {"retention_concept": "Rendimientos financieros de títulos de renta fija", "taxpayer_type": "todos", "minimum_base_uvt": 0, "minimum_base_pesos": 0, "rate_percentage": 4.0},
    {"retention_concept": "Loterías, rifas, apuestas y similares", "taxpayer_type": "todos", "minimum_base_uvt": 48, "minimum_base_pesos": 2513952, "rate_percentage": 20.0},
    {"retention_concept": "Contratos de construcción y urbanización", "taxpayer_type": "todos", "minimum_base_uvt": 27, "minimum_base_pesos": 1414098, "rate_percentage": 2.0},
]
