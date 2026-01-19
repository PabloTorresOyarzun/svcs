import base64
import logging
from typing import Dict, List, Optional
from litestar import Router, get, post, Request
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR

from config.settings import get_settings
from middleware import verify_api_token
from schemas import (
    ProcesamientoResponse, DocumentoFinal, Alerta, CacheInfo, 
    DocumentoSimplificado, Usuarios
)
from services.legacy_service import consultar_despacho_detalle, consultar_documentacion
from services.azure_service import eliminar_campos_vacios
from services.pdf_service import convertir_excel_a_pdf, convertir_imagen_a_pdf
from services.document_service import (
    clasificar_pdf_completo, procesar_pdf_completo, serializar_documentos_para_cache
)
from utils.validators import (
    validar_tamano_archivo, es_archivo_excel, es_archivo_imagen, 
    validar_excel, validar_imagen, validar_pdf
)
from database.connection import cache_repo, calcular_hash_documentos, calcular_hash_archivo

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory storage for processed documents (migrated from main.py)
documentos_finales_sgd: Dict[str, List[Dict]] = {}

@get("/consultar/{codigo_despacho:str}")
async def consultar_despacho(request: Request, codigo_despacho: str) -> dict:
    """Consulta la información del despacho y lista los documentos disponibles."""
    verify_api_token(request)
    
    if not settings.BEARER_TOKEN:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="BEARER_TOKEN no configurado")
    
    datos_despacho_detalle = await consultar_despacho_detalle(codigo_despacho, settings.BEARER_TOKEN)
    
    if datos_despacho_detalle and "data" in datos_despacho_detalle:
        despacho_data = datos_despacho_detalle["data"]
        
        if isinstance(despacho_data, dict):
            codigo_visible = str(despacho_data.get("codigo", "N/A"))
            cliente = despacho_data.get("cliente", {})
            cliente_nombre = cliente.get("nombre", "N/A") if isinstance(cliente, dict) else "N/A"
            
            documentos_list = despacho_data.get("documentos", [])
            if not isinstance(documentos_list, list):
                documentos_list = []
            
            documentos_simplificados = []
            for doc in documentos_list:
                if isinstance(doc, dict):
                    tipo = doc.get("tipo", {})
                    documentos_simplificados.append({
                        "nombre": tipo.get("nombre", "Sin nombre") if isinstance(tipo, dict) else "Sin nombre",
                        "estado": doc.get("estado", "N/A"),
                        "fecha_recepcion": doc.get("fecha_recepcion", "N/A")
                    })
            
            usuarios_list = despacho_data.get("usuarios", [])
            if not isinstance(usuarios_list, list):
                usuarios_list = []
            
            pedidores = []
            jefes_operaciones = []
            
            for user in usuarios_list:
                if isinstance(user, dict):
                    role_name = user.get("role_name", "")
                    nombre = user.get("name", "")
                    
                    if role_name in ("pedidor", "pedidor_exportaciones"):
                        pedidores.append(nombre)
                    elif role_name == "jefe_operaciones":
                        jefes_operaciones.append(nombre)
            
            usuarios_datos = {
                "pedidor": pedidores if pedidores else None,
                "jefe_operaciones": jefes_operaciones if jefes_operaciones else None
            }
            
            return {
                "codigo_despacho": codigo_visible,
                "id_interno": str(despacho_data.get("id", "N/A")),
                "cliente": cliente_nombre,
                "estado": despacho_data.get("estado_despacho", "N/A"),
                "tipo": despacho_data.get("tipo_despacho", "N/A"),
                "total_documentos": len(documentos_simplificados),
                "documentos": documentos_simplificados,
                "usuarios": usuarios_datos
            }
    
    documentos_base64_list = await consultar_documentacion(codigo_despacho, settings.BEARER_TOKEN)
    
    if documentos_base64_list and isinstance(documentos_base64_list, list):
        documentos_info = []
        for doc in documentos_base64_list:
            if isinstance(doc, dict):
                documentos_info.append({
                    "nombre": doc.get("nombre_documento", "Sin nombre"),
                    "documento_id": doc.get("documento_id", "N/A")
                })
        
        return {
            "codigo": codigo_despacho,
            "mensaje": "Información limitada: solo se encontraron documentos",
            "total_documentos": len(documentos_info),
            "documentos": documentos_info
        }
    
    raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Despacho no encontrado")


@post("/clasificar/{codigo_despacho:str}")
async def clasificar_despacho(
    request: Request, 
    codigo_despacho: str,
    force: bool = False
) -> ProcesamientoResponse:
    verify_api_token(request)
    
    if not settings.BEARER_TOKEN:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="BEARER_TOKEN no configurado")

    datos_despacho_detalle = await consultar_despacho_detalle(codigo_despacho, settings.BEARER_TOKEN)

    codigo_visible = None
    cliente_nombre = "N/A"
    estado_despacho = "N/A"
    tipo_despacho = "N/A"

    if datos_despacho_detalle and "data" in datos_despacho_detalle:
        despacho_data = datos_despacho_detalle["data"]
        if isinstance(despacho_data, dict):
            codigo_visible = str(despacho_data.get("codigo", ""))
            cliente = despacho_data.get("cliente", {})
            cliente_nombre = cliente.get("nombre", "N/A") if isinstance(cliente, dict) else "N/A"
            estado_despacho = despacho_data.get("estado_despacho", "N/A")
            tipo_despacho = despacho_data.get("tipo_despacho", "N/A")

    documentos_base64_list = None

    if codigo_visible:
        documentos_base64_list = await consultar_documentacion(codigo_visible, settings.BEARER_TOKEN)

    if not documentos_base64_list:
        documentos_base64_list = await consultar_documentacion(codigo_despacho, settings.BEARER_TOKEN)

    if not documentos_base64_list or not isinstance(documentos_base64_list, list):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No se pudieron obtener los documentos")

    # Calcular hash de documentos actuales
    documentos_hash = calcular_hash_documentos(documentos_base64_list)

    # Verificar caché si está habilitado y no se fuerza reprocesamiento
    cache_info = None
    if settings.CACHE_ENABLED and not force:
        try:
            estado_cache = await cache_repo.verificar_cambios_despacho(
                codigo_despacho, "clasificar", documentos_hash
            )
            
            if estado_cache["existe_cache"] and not estado_cache["hay_cambios"]:
                # Retornar desde caché
                cached = await cache_repo.obtener_despacho(
                    codigo_despacho, "clasificar", documentos_hash
                )
                if cached:
                    logger.info(f"Retornando clasificación desde caché para {codigo_despacho}")
                    docs_response = [
                        DocumentoFinal(**doc) for doc in cached["resultado"]["documentos"]
                    ]
                    return ProcesamientoResponse(
                        codigo_despacho=codigo_despacho,
                        cliente=cached["cliente"],
                        estado=cached["estado"],
                        tipo=cached["tipo"],
                        total_documentos_segmentados=cached["total_documentos_segmentados"],
                        documentos=docs_response,
                        cache_info=CacheInfo(
                            desde_cache=True,
                            hash_documentos=documentos_hash,
                            fecha_cache=str(cached["updated_at"]),
                            hay_cambios=False
                        )
                    )
            
            # Hay cambios o no existe caché
            cache_info = CacheInfo(
                desde_cache=False,
                hash_documentos=documentos_hash,
                hay_cambios=estado_cache.get("hay_cambios", True)
            )
        except Exception as e:
            logger.warning(f"Error consultando caché: {e}")
            cache_info = CacheInfo(desde_cache=False, hash_documentos=documentos_hash)

    # Procesar documentos
    todos_documentos_finales = []

    for doc in documentos_base64_list:
        if isinstance(doc, dict):
            base64_data = doc.get("documento", "")

            if ',' in base64_data:
                _, base64_content = base64_data.split(',', 1)
            else:
                base64_content = base64_data

            try:
                file_bytes = base64.b64decode(base64_content)
                nombre_documento = doc.get("nombre_documento", "documento.pdf")

                validar_tamano_archivo(file_bytes)

                if es_archivo_excel(nombre_documento):
                    if not validar_excel(file_bytes, nombre_documento):
                        continue
                    try:
                        pdf_bytes = await convertir_excel_a_pdf(file_bytes, nombre_documento)
                        nombre_procesamiento = nombre_documento.rsplit('.', 1)[0] + '.pdf'
                    except Exception:
                        continue
                elif es_archivo_imagen(nombre_documento):
                    if not validar_imagen(file_bytes, nombre_documento):
                        continue
                    try:
                        pdf_bytes = await convertir_imagen_a_pdf(file_bytes, nombre_documento)
                        nombre_procesamiento = nombre_documento.rsplit('.', 1)[0] + '.pdf'
                    except Exception:
                        continue
                else:
                    if not validar_pdf(file_bytes):
                        continue
                    pdf_bytes = file_bytes
                    nombre_procesamiento = nombre_documento

                resultado = await clasificar_pdf_completo(pdf_bytes, nombre_procesamiento)

                if resultado["error"]:
                    continue

                todos_documentos_finales.extend(resultado["documentos_finales"])

            except Exception:
                continue

    documentos_finales_sgd[codigo_despacho] = todos_documentos_finales

    docs_response = []
    for doc_final in todos_documentos_finales:
        datos_limpios = None
        if doc_final.get("datos_extraidos"):
             datos_limpios = eliminar_campos_vacios(doc_final.get("datos_extraidos"))

        docs_response.append(DocumentoFinal(
            archivo_origen=doc_final["archivo_origen"],
            nombre_salida=doc_final["nombre_salida"],
            tipo=doc_final["tipo"],
            paginas=doc_final["paginas"],
            alertas=[Alerta(**alerta) for alerta in doc_final["alertas"]] if doc_final["alertas"] else None,
            datos_extraidos=datos_limpios
        ))

    # Guardar en caché
    if settings.CACHE_ENABLED:
        try:
            await cache_repo.guardar_despacho(
                codigo_despacho=codigo_despacho,
                tipo_operacion="clasificar",
                documentos_hash=documentos_hash,
                cliente=cliente_nombre,
                estado=estado_despacho,
                tipo=tipo_despacho,
                total_documentos_segmentados=len(docs_response),
                resultado={"documentos": [doc.model_dump() for doc in docs_response]}
            )
        except Exception as e:
            logger.warning(f"Error guardando en caché: {e}")

    return ProcesamientoResponse(
        codigo_despacho=codigo_despacho,
        cliente=cliente_nombre,
        estado=estado_despacho,
        tipo=tipo_despacho,
        total_documentos_segmentados=len(docs_response),
        documentos=docs_response,
        cache_info=cache_info
    )


@post("/procesar/{codigo_despacho:str}")
async def procesar_despacho(
    request: Request, 
    codigo_despacho: str,
    force: bool = False
) -> ProcesamientoResponse:
    verify_api_token(request)
    
    if not settings.BEARER_TOKEN:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="BEARER_TOKEN no configurado")
    
    datos_despacho_detalle = await consultar_despacho_detalle(codigo_despacho, settings.BEARER_TOKEN)
    
    codigo_visible = None
    cliente_nombre = "N/A"
    estado_despacho = "N/A"
    tipo_despacho = "N/A"
    
    if datos_despacho_detalle and "data" in datos_despacho_detalle:
        despacho_data = datos_despacho_detalle["data"]
        if isinstance(despacho_data, dict):
            codigo_visible = str(despacho_data.get("codigo", ""))
            cliente = despacho_data.get("cliente", {})
            cliente_nombre = cliente.get("nombre", "N/A") if isinstance(cliente, dict) else "N/A"
            estado_despacho = despacho_data.get("estado_despacho", "N/A")
            tipo_despacho = despacho_data.get("tipo_despacho", "N/A")
    
    documentos_base64_list = None
    
    if codigo_visible:
        documentos_base64_list = await consultar_documentacion(codigo_visible, settings.BEARER_TOKEN)
    
    if not documentos_base64_list:
        documentos_base64_list = await consultar_documentacion(codigo_despacho, settings.BEARER_TOKEN)
    
    if not documentos_base64_list or not isinstance(documentos_base64_list, list):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No se pudieron obtener los documentos")
    
    # Calcular hash de documentos actuales
    documentos_hash = calcular_hash_documentos(documentos_base64_list)

    # Verificar caché si está habilitado y no se fuerza reprocesamiento
    cache_info = None
    if settings.CACHE_ENABLED and not force:
        try:
            estado_cache = await cache_repo.verificar_cambios_despacho(
                codigo_despacho, "procesar", documentos_hash
            )
            
            if estado_cache["existe_cache"] and not estado_cache["hay_cambios"]:
                cached = await cache_repo.obtener_despacho(
                    codigo_despacho, "procesar", documentos_hash
                )
                if cached:
                    logger.info(f"Retornando procesamiento desde caché para {codigo_despacho}")
                    docs_response = [
                        DocumentoFinal(**doc) for doc in cached["resultado"]["documentos"]
                    ]
                    return ProcesamientoResponse(
                        codigo_despacho=codigo_despacho,
                        cliente=cached["cliente"],
                        estado=cached["estado"],
                        tipo=cached["tipo"],
                        total_documentos_segmentados=cached["total_documentos_segmentados"],
                        documentos=docs_response,
                        cache_info=CacheInfo(
                            desde_cache=True,
                            hash_documentos=documentos_hash,
                            fecha_cache=str(cached["updated_at"]),
                            hay_cambios=False
                        )
                    )
            
            cache_info = CacheInfo(
                desde_cache=False,
                hash_documentos=documentos_hash,
                hay_cambios=estado_cache.get("hay_cambios", True)
            )
        except Exception as e:
            logger.warning(f"Error consultando caché: {e}")
            cache_info = CacheInfo(desde_cache=False, hash_documentos=documentos_hash)

    todos_documentos_finales = []
    
    for doc in documentos_base64_list:
        if isinstance(doc, dict):
            base64_data = doc.get("documento", "")
            
            if ',' in base64_data:
                _, base64_content = base64_data.split(',', 1)
            else:
                base64_content = base64_data
            
            try:
                file_bytes = base64.b64decode(base64_content)
                nombre_documento = doc.get("nombre_documento", "documento.pdf")
                
                validar_tamano_archivo(file_bytes)

                if es_archivo_excel(nombre_documento):
                    if not validar_excel(file_bytes, nombre_documento):
                        continue
                    try:
                        pdf_bytes = await convertir_excel_a_pdf(file_bytes, nombre_documento)
                        nombre_procesamiento = nombre_documento.rsplit('.', 1)[0] + '.pdf'
                    except Exception:
                        continue
                elif es_archivo_imagen(nombre_documento):
                    if not validar_imagen(file_bytes, nombre_documento):
                        continue
                    try:
                        pdf_bytes = await convertir_imagen_a_pdf(file_bytes, nombre_documento)
                        nombre_procesamiento = nombre_documento.rsplit('.', 1)[0] + '.pdf'
                    except Exception:
                        continue
                else:
                    if not validar_pdf(file_bytes):
                        continue
                    pdf_bytes = file_bytes
                    nombre_procesamiento = nombre_documento

                resultado = await procesar_pdf_completo(pdf_bytes, nombre_procesamiento)
                
                if resultado["error"]:
                    continue
                
                todos_documentos_finales.extend(resultado["documentos_finales"])
                
            except Exception:
                continue
    
    documentos_finales_sgd[codigo_despacho] = todos_documentos_finales
    
    docs_response = []
    for doc_final in todos_documentos_finales:
        datos_limpios = None
        if doc_final.get("datos_extraidos"):
             datos_limpios = eliminar_campos_vacios(doc_final.get("datos_extraidos"))

        docs_response.append(DocumentoFinal(
            archivo_origen=doc_final["archivo_origen"],
            nombre_salida=doc_final["nombre_salida"],
            tipo=doc_final["tipo"],
            paginas=doc_final["paginas"],
            alertas=[Alerta(**alerta) for alerta in doc_final["alertas"]] if doc_final["alertas"] else None,
            datos_extraidos=datos_limpios
        ))

    # Guardar en caché
    if settings.CACHE_ENABLED:
        try:
            await cache_repo.guardar_despacho(
                codigo_despacho=codigo_despacho,
                tipo_operacion="procesar",
                documentos_hash=documentos_hash,
                cliente=cliente_nombre,
                estado=estado_despacho,
                tipo=tipo_despacho,
                total_documentos_segmentados=len(docs_response),
                resultado={"documentos": [doc.model_dump() for doc in docs_response]}
            )
        except Exception as e:
            logger.warning(f"Error guardando en caché: {e}")

    return ProcesamientoResponse(
        codigo_despacho=codigo_despacho,
        cliente=cliente_nombre,
        estado=estado_despacho,
        tipo=tipo_despacho,
        total_documentos_segmentados=len(docs_response),
        documentos=docs_response,
        cache_info=cache_info
    )

sgd_router = Router(
    path="/sgd",
    route_handlers=[consultar_despacho, clasificar_despacho, procesar_despacho],
    tags=["SGD"]
)
