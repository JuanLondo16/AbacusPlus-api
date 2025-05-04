from fastapi import FastAPI, HTTPException, status
from app.api.endpoints.xml import router as xml_router
from app.api.endpoints.users import router as users_router

app = FastAPI(
    title="XML Reader API",
    description="API para procesamiento de archivos XML y ZIP",
    version="1.0.0"
)

# Incluir routers
app.include_router(xml_router, prefix="/api/v1", tags=["xml"])
app.include_router(users_router, prefix="/api/v1", tags=["users"])

@app.get("/")
async def read_root():
    return {"message": "Bienvenido a la API de Procesamiento de XML"}

@app.get("/health")
async def health_check():
    """
    Endpoint de verificación de estado.
    
    Returns:
        Estado de la API
    """
    return {"status": "healthy"}

@app.get("/{path:path}")
async def not_found(path: str):
    """
    Maneja rutas no encontradas.
    
    Args:
        path: Ruta solicitada
        
    Returns:
        Respuesta 404 con mensaje de error
    """
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Ruta no encontrada: {path}"
    )