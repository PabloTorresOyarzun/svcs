from typing import List, Optional
from litestar import Router, get, post, delete, Request
from litestar.status_codes import HTTP_200_OK, HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR
from litestar.exceptions import HTTPException

from config.settings import get_settings, get_valid_api_tokens
from middleware import verify_admin_token
from schemas import TokenInfo, TokenCreateRequest, TokenCreateResponse, TokenDeleteResponse
from database.connection import cache_repo
from services.token_service import token_manager

settings = get_settings()

@get("/")
async def listar_tokens(request: Request) -> List[TokenInfo]:
    """Lista todos los tokens de la API con su metadata."""
    verify_admin_token(request)
    
    tokens = token_manager.list_tokens()

    env_tokens = get_valid_api_tokens()
    for idx, token_value in enumerate(env_tokens, start=1):
        masked_token = f"{token_value[:8]}...{token_value[-4:]}" if len(token_value) > 12 else "***"

        tokens.append({
            "id": f"env-token-{idx}",
            "name": f"Token de .env #{idx}",
            "masked_token": masked_token,
            "created_at": "N/A",
            "created_by": "env-config",
            "last_used": None,
            "is_active": True
        })

    return [TokenInfo(**t) for t in tokens]


@post("/generate")
async def generar_token(request: Request, data: TokenCreateRequest) -> TokenCreateResponse:
    """Genera un nuevo token de autenticación API."""
    verify_admin_token(request)
    
    result = token_manager.generate_token(
        name=data.name,
        created_by="admin"
    )
    return TokenCreateResponse(**result)


@delete("/{token_id:str}", status_code=HTTP_200_OK)
async def eliminar_token(request: Request, token_id: str) -> TokenDeleteResponse:
    """Elimina un token por su ID."""
    verify_admin_token(request)
    
    success = token_manager.delete_token(token_id)

    if success:
        return TokenDeleteResponse(
            success=True,
            message=f"Token {token_id} eliminado exitosamente"
        )
    else:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Token {token_id} no encontrado"
        )


@delete("/cache/despacho/{codigo_despacho:str}", status_code=HTTP_200_OK)
async def eliminar_cache_despacho(
    request: Request, 
    codigo_despacho: str,
    tipo_operacion: Optional[str] = None
) -> dict:
    """Elimina el caché de un despacho específico."""
    verify_admin_token(request)
    
    try:
        count = await cache_repo.eliminar_cache_despacho(codigo_despacho, tipo_operacion)
        return {
            "success": True,
            "message": f"Eliminados {count} registros de caché",
            "codigo_despacho": codigo_despacho
        }
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error eliminando caché: {str(e)}"
        )


admin_router = Router(
    path="/admin/tokens",
    route_handlers=[listar_tokens, generar_token, eliminar_token],
    tags=["Admin - Gestión de Tokens"]
)

cache_router = Router(
    path="/admin",
    route_handlers=[eliminar_cache_despacho],
    tags=["Admin - Gestión de Caché"]
)
