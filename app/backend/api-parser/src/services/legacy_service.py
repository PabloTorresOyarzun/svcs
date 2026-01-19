from typing import Dict, List, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import get_settings

settings = get_settings()

BASE_URL = "https://backend.juanleon.cl"
ENDPOINT_DESPACHO = "/api/admin/despachos/{codigo}"
ENDPOINT_DOCUMENTOS = "/api/admin/documentos64/despacho/{codigo_visible}"

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
)
async def consultar_despacho_detalle(codigo_interno: str, token: str) -> Optional[Dict]:
    if not token:
        return None
    
    url = f"{BASE_URL}{ENDPOINT_DESPACHO.format(codigo=str(codigo_interno))}"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    timeout = httpx.Timeout(
        connect=settings.TIMEOUT_CONNECT,
        read=settings.TIMEOUT_READ,
        write=settings.TIMEOUT_WRITE,
        pool=5.0
    )
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            if 'application/json' not in response.headers.get('Content-Type', ''):
                return None
            
            datos = response.json()
            return datos if isinstance(datos, dict) else None
    except (httpx.TimeoutException, httpx.NetworkError):
        raise
    except Exception:
        return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
)
async def consultar_documentacion(codigo: str, token: str) -> Optional[List]:
    if not token:
        return None
    
    url = f"{BASE_URL}{ENDPOINT_DOCUMENTOS.format(codigo_visible=str(codigo))}"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    timeout = httpx.Timeout(
        connect=settings.TIMEOUT_CONNECT,
        read=settings.TIMEOUT_READ,
        write=settings.TIMEOUT_WRITE,
        pool=5.0
    )
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            if 'application/json' not in response.headers.get('Content-Type', ''):
                return None
            
            datos_json = response.json()
            if not isinstance(datos_json, dict):
                return None
            
            documentos = datos_json.get("data", [])
            return documentos if isinstance(documentos, list) else None
    except (httpx.TimeoutException, httpx.NetworkError):
        raise
    except Exception:
        return None
