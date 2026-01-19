import httpx
import logging
import asyncio
from typing import Any, Dict, Optional
from litestar.exceptions import HTTPException

from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

API_VERSION = "2024-11-30"

def get_azure_headers() -> Dict[str, str]:
    """Retorna headers para autenticación con Azure DI Cloud."""
    return {
        "Ocp-Apim-Subscription-Key": settings.AZURE_KEY,
        "Content-Type": "application/pdf"
    }


def get_azure_base_url() -> str:
    """Retorna la URL base de Azure DI."""
    endpoint = settings.AZURE_ENDPOINT.rstrip('/')
    return f"{endpoint}/documentintelligence"


def limpiar_datos_azure(data: Any) -> Any:
    """
    Limpia recursivamente la respuesta de Azure DI para eliminar metadata
    (polygons, spans, confidence) y dejar solo los valores.
    """
    if isinstance(data, list):
        return [limpiar_datos_azure(item) for item in data]
    
    if isinstance(data, dict):
        if "valueString" in data: return data["valueString"]
        if "valueNumber" in data: return data["valueNumber"]
        if "valueDate" in data: return data["valueDate"]
        if "valueTime" in data: return data["valueTime"]
        if "valuePhoneNumber" in data: return data["valuePhoneNumber"]
        if "valueBoolean" in data: return data["valueBoolean"]
        if "valueSelectionMark" in data: return data["valueSelectionMark"]
        
        if "valueArray" in data:
            return limpiar_datos_azure(data["valueArray"])
        if "valueObject" in data:
            return {k: limpiar_datos_azure(v) for k, v in data["valueObject"].items()}
        
        cleaned = {}
        for k, v in data.items():
            if k in ["boundingRegions", "polygon", "spans", "confidence", "type"]:
                continue
            cleaned[k] = limpiar_datos_azure(v)
        
        if not cleaned and "content" in data:
            return data["content"]
            
        return cleaned

    return data


def eliminar_campos_vacios(data: Any) -> Any:
    """
    Elimina recursivamente claves con valores None, {}, [] o strings vacíos.
    """
    if isinstance(data, dict):
        cleaned = {
            k: eliminar_campos_vacios(v)
            for k, v in data.items()
        }
        return {
            k: v for k, v in cleaned.items() 
            if v not in [None, {}, [], ""]
        }
    
    elif isinstance(data, list):
        cleaned = [eliminar_campos_vacios(item) for item in data]
        return [item for item in cleaned if item not in [None, {}, [], ""]]
        
    return data


async def verificar_modelo_entrenado(model_id: str) -> bool:
    """Verifica si un modelo custom está entrenado en Azure DI Cloud."""
    base_url = get_azure_base_url()
    url = f"{base_url}/documentModels/{model_id}?api-version={API_VERSION}"

    headers = {
        "Ocp-Apim-Subscription-Key": settings.AZURE_KEY
    }

    timeout_config = httpx.Timeout(
        connect=settings.TIMEOUT_CONNECT,
        read=settings.TIMEOUT_READ,
        write=settings.TIMEOUT_WRITE,
        pool=5.0
    )

    try:
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                logger.info(f"Modelo {model_id} verificado en Azure Cloud")
                return True
            else:
                logger.warning(f"Modelo {model_id} no encontrado: {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"Error verificando modelo {model_id}: {str(e)}")
        return False


async def extraer_datos_con_modelo(pdf_bytes: bytes, model_id: str) -> Optional[Dict[str, Any]]:
    """Extrae datos estructurados de un PDF usando un modelo custom de Azure DI Cloud."""
    base_url = get_azure_base_url()
    url = f"{base_url}/documentModels/{model_id}:analyze?api-version={API_VERSION}"

    headers = get_azure_headers()

    timeout_config = httpx.Timeout(
        connect=settings.TIMEOUT_CONNECT,
        read=300.0,
        write=settings.TIMEOUT_WRITE,
        pool=5.0
    )

    try:
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            logger.info(f"Enviando documento a modelo {model_id} en Azure Cloud")
            response = await client.post(url, headers=headers, content=pdf_bytes)

            if response.status_code != 202:
                logger.warning(f"Error iniciando análisis: {response.status_code} - {response.text[:500]}")
                return None

            operation_location = response.headers.get('Operation-Location')
            if not operation_location:
                logger.warning("No se recibió Operation-Location")
                return None

            logger.info(f"Análisis iniciado, polling: {operation_location}")

            poll_headers = {
                "Ocp-Apim-Subscription-Key": settings.AZURE_KEY
            }

            max_intentos = 60
            for intento in range(max_intentos):
                status_response = await client.get(operation_location, headers=poll_headers)

                if status_response.status_code != 200:
                    logger.warning(f"Error en polling: {status_response.status_code}")
                    return None

                resultado = status_response.json()
                status = resultado.get('status')

                if status == 'succeeded':
                    analyze_result = resultado.get('analyzeResult', {})
                    documentos = analyze_result.get('documents', [])
                    
                    logger.info(f"Análisis exitoso. Documentos encontrados: {len(documentos)}")

                    if documentos:
                        fields = documentos[0].get('fields', {})
                        logger.info(f"Campos extraídos: {list(fields.keys())}")

                        datos_aplanados = {
                            k: limpiar_datos_azure(v) for k, v in fields.items()
                        }

                        datos_finales = eliminar_campos_vacios(datos_aplanados)

                        return datos_finales
                    return {}

                elif status == 'failed':
                    error = resultado.get('error', {})
                    logger.error(f"Análisis fallido: {error}")
                    return None

                await asyncio.sleep(2)

            logger.warning("Timeout en análisis")
            return None

    except Exception as e:
        logger.error(f"Error en extracción: {str(e)}")
        return None
