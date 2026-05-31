from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.application.dto.product import ImportProductsResponse, ProductResponse
from app.application.use_cases.import_products import ImportProductsUseCase
from app.dependencies import get_import_products_use_case, get_product_repository
from app.infrastructure.persistence.repositories.product_repository import ProductRepository

router = APIRouter()

PRODUCTS_EXCEL_STRUCTURE = """
Estructura del Excel:

| Columna     | Obligatoria | Ejemplo                      | Descripcion                              |
| ----------- | ----------- | ---------------------------- | ---------------------------------------- |
| `code`      | Si          | `P-001`                      | Codigo unico del producto o servicio.    |
| `type`      | Si          | `product`                    | Tipo: `product` o `service`.             |
| `description` | Si        | `Licencia de software anual` | Descripcion del producto o servicio.     |
| `active`    | No          | `true`                       | Estado. Si se omite, queda `true`.       |

Valores booleanos aceptados: `true`, `false`, `1`, `0`, `yes`, `no`, `si`, `sí`, `x`.
"""


@router.get(
    "/integrations/products",
    response_model=list[ProductResponse],
    status_code=status.HTTP_200_OK,
    summary="Listar productos y servicios",
    description=(
        "Retorna todos los productos y servicios registrados en la tabla local `integration_products`.\n\n"
        "Usa el filtro `active` para obtener solo los activos o solo los inactivos.\n\n"
        "Usa el filtro `type` para obtener solo productos (`product`) o solo servicios (`service`)."
    ),
    response_description="Lista de productos ordenada por codigo.",
)
def list_products(
    active: Optional[bool] = Query(
        None, description="Filtrar por estado activo. Si se omite, retorna todos."
    ),
    type: Optional[str] = Query(None, description="Filtrar por tipo: 'product' o 'service'."),
    repository: ProductRepository = Depends(get_product_repository),
) -> list[ProductResponse]:
    products = repository.list(active=active)
    if type is not None:
        products = [p for p in products if p.type == type.strip().lower()]
    return products


@router.post(
    "/integrations/products/imports",
    response_model=ImportProductsResponse,
    status_code=status.HTTP_200_OK,
    summary="Importar productos y servicios desde Excel",
    description=(
        "Recibe un archivo `.xlsx` con productos o servicios y alimenta "
        "la tabla local `integration_products`.\n\n"
        "La operacion es idempotente por `code`: si el producto ya existe, "
        "actualiza sus datos; si no existe, lo crea.\n\n"
        f"{PRODUCTS_EXCEL_STRUCTURE}"
    ),
    response_description="Resumen de productos importados y listado resultante.",
    responses={
        400: {
            "description": "Archivo invalido, columnas faltantes, tipo invalido o filas con datos incorrectos."
        },
    },
)
async def import_products_from_excel(
    sheet_name: Optional[str] = Form(
        None, description="Nombre de hoja a leer. Si se omite, usa la primera hoja."
    ),
    file: UploadFile = File(..., description="Archivo Excel .xlsx con los productos."),
    use_case: ImportProductsUseCase = Depends(get_import_products_use_case),
) -> ImportProductsResponse:
    content = await file.read()
    return use_case.execute(
        sheet_name=sheet_name,
        file_content=content,
    )
