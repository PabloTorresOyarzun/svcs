import sys
import io
from contextlib import contextmanager
from litestar import Request
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN, HTTP_500_INTERNAL_SERVER_ERROR

# Ajustar imports asumiendo que config.py y token_manager.py están en el root
from config.settings import get_settings, get_valid_api_tokens
from services.token_service import token_manager

settings = get_settings()

@contextmanager
def suprimir_prints():
    """Suprime temporalmente la salida a stdout."""
    original_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = original_stdout


def get_bearer_token(request: Request) -> str:
    """Extrae el token Bearer del header Authorization."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Token de autenticación requerido")
    return auth_header[7:]


def verify_api_token(request: Request) -> str:
    """Verifica que el token API proporcionado sea válido."""
    token = get_bearer_token(request)
    
    if settings.ADMIN_TOKEN and token == settings.ADMIN_TOKEN:
        return token

    if token_manager.is_valid_token(token):
        return token

    valid_tokens = get_valid_api_tokens()
    if valid_tokens and token in valid_tokens:
        return token

    raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Token de autenticación inválido")


def verify_admin_token(request: Request) -> str:
    """Verifica que el token de administrador sea válido."""
    token = get_bearer_token(request)
    
    if not settings.ADMIN_TOKEN:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="ADMIN_TOKEN no configurado en el servidor")

    if token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Se requiere token de administrador")

    return token
