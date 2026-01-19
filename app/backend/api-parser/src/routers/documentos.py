import logging
from typing import Dict, List, Annotated
from litestar import Router, post, Request
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.params import Body

from config.settings import get_settings
from middleware import verify_api_token
from schemas import (
    ProcesamientoIndividualResponse, DocumentoFinal, Alerta, CacheInfo
)
from services.azure_service import eliminar_campos_vacios
from services.pdf_service import convertir_excel_a_pdf, convertir_imagen_a_pdf
from services.document_service import (
    clasificar_pdf_completo, procesar_pdf_completo
)
from utils.validators import (
    validar_tamano_archivo, es_archivo_excel, es_archivo_imagen, 
    validar_excel, validar_imagen, validar_pdf
)
from database.connection import cache_repo, calcular_hash_archivo

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory storage for processed individual documents
documentos_finales_individuales: Dict[str, List[Dict]] = {}

@post("/clasificar")
async def clasificar_documento_individual(
    request: Request,
    data: Annotated[UploadFile, Body(media_type=RequestEncodingType.MULTI_PART)],
    force: bool = False
) -> ProcesamientoIndividualResponse:
    verify_api_token(request)
    
    nombre_archivo = data.filename.lower()
    es_pdf = nombre_archivo.endswith('.pdf')
    es_excel = es_archivo_excel(data.filename)
    es_imagen = es_archivo_imagen(data.filename)

    if not es_pdf and not es_excel and not es_imagen:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Solo se aceptan archivos PDF, Excel (.xls, .xlsx, .xlsm, .xlsb, .xltx, .xltm) o imágenes (.jpg, .jpeg, .png, .gif, .bmp, .tiff, .webp)"
        )

    try:
        file_bytes = await data.read()
        archivo_hash = calcular_hash_archivo(file_bytes)

        validar_tamano_archivo(file_bytes)

        # Verificar caché
        cache_info = None
        if settings.CACHE_ENABLED and not force:
            try:
                cached = await cache_repo.obtener_documento(archivo_hash, "clasificar")
                if cached:
                    logger.info(f"Retornando clasificación desde caché para {data.filename}")
                    docs_response = [
                        DocumentoFinal(**doc) for doc in cached["resultado"]["documentos"]
                    ]
                    return ProcesamientoIndividualResponse(
                        archivo_origen=data.filename,
                        total_documentos_segmentados=cached["total_documentos_segmentados"],
                        documentos=docs_response,
                        cache_info=CacheInfo(
                            desde_cache=True,
                            hash_documentos=archivo_hash,
                            fecha_cache=str(cached["updated_at"])
                        )
                    )
                cache_info = CacheInfo(desde_cache=False, hash_documentos=archivo_hash)
            except Exception as e:
                logger.warning(f"Error consultando caché: {e}")
                cache_info = CacheInfo(desde_cache=False, hash_documentos=archivo_hash)

        if es_excel:
            if not validar_excel(file_bytes, data.filename):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail="El archivo no es un Excel válido"
                )
            pdf_bytes = await convertir_excel_a_pdf(file_bytes, data.filename)
            nombre_procesamiento = data.filename.rsplit('.', 1)[0] + '.pdf'
        elif es_imagen:
            if not validar_imagen(file_bytes, data.filename):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail="El archivo no es una imagen válida"
                )
            pdf_bytes = await convertir_imagen_a_pdf(file_bytes, data.filename)
            nombre_procesamiento = data.filename.rsplit('.', 1)[0] + '.pdf'
        else:
            if not validar_pdf(file_bytes):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail="El archivo no es un PDF válido"
                )
            pdf_bytes = file_bytes
            nombre_procesamiento = data.filename

        resultado = await clasificar_pdf_completo(pdf_bytes, nombre_procesamiento)

        if resultado["error"]:
            raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al clasificar: {resultado['error']}")

        documentos_finales_individuales[data.filename] = resultado["documentos_finales"]

        docs_response = []
        for doc_final in resultado["documentos_finales"]:
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
                await cache_repo.guardar_documento(
                    archivo_hash=archivo_hash,
                    nombre_archivo=data.filename,
                    tipo_operacion="clasificar",
                    total_documentos_segmentados=len(docs_response),
                    resultado={"documentos": [doc.model_dump() for doc in docs_response]}
                )
            except Exception as e:
                logger.warning(f"Error guardando en caché: {e}")

        return ProcesamientoIndividualResponse(
            archivo_origen=data.filename,
            total_documentos_segmentados=len(docs_response),
            documentos=docs_response,
            cache_info=cache_info
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al clasificar documento: {str(e)}")


@post("/procesar")
async def procesar_documento_individual(
    request: Request,
    data: Annotated[UploadFile, Body(media_type=RequestEncodingType.MULTI_PART)],
    force: bool = False
) -> ProcesamientoIndividualResponse:
    verify_api_token(request)
    
    nombre_archivo = data.filename.lower()
    es_pdf = nombre_archivo.endswith('.pdf')
    es_excel = es_archivo_excel(data.filename)
    es_imagen = es_archivo_imagen(data.filename)

    if not es_pdf and not es_excel and not es_imagen:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Solo se aceptan archivos PDF, Excel (.xls, .xlsx, .xlsm, .xlsb, .xltx, .xltm) o imágenes (.jpg, .jpeg, .png, .gif, .bmp, .tiff, .webp)"
        )

    try:
        file_bytes = await data.read()
        archivo_hash = calcular_hash_archivo(file_bytes)

        validar_tamano_archivo(file_bytes)

        # Verificar caché
        cache_info = None
        if settings.CACHE_ENABLED and not force:
            try:
                cached = await cache_repo.obtener_documento(archivo_hash, "procesar")
                if cached:
                    logger.info(f"Retornando procesamiento desde caché para {data.filename}")
                    docs_response = [
                        DocumentoFinal(**doc) for doc in cached["resultado"]["documentos"]
                    ]
                    return ProcesamientoIndividualResponse(
                        archivo_origen=data.filename,
                        total_documentos_segmentados=cached["total_documentos_segmentados"],
                        documentos=docs_response,
                        cache_info=CacheInfo(
                            desde_cache=True,
                            hash_documentos=archivo_hash,
                            fecha_cache=str(cached["updated_at"])
                        )
                    )
                cache_info = CacheInfo(desde_cache=False, hash_documentos=archivo_hash)
            except Exception as e:
                logger.warning(f"Error consultando caché: {e}")
                cache_info = CacheInfo(desde_cache=False, hash_documentos=archivo_hash)

        if es_excel:
            if not validar_excel(file_bytes, data.filename):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail="El archivo no es un Excel válido"
                )
            pdf_bytes = await convertir_excel_a_pdf(file_bytes, data.filename)
            nombre_procesamiento = data.filename.rsplit('.', 1)[0] + '.pdf'
        elif es_imagen:
            if not validar_imagen(file_bytes, data.filename):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail="El archivo no es una imagen válida"
                )
            pdf_bytes = await convertir_imagen_a_pdf(file_bytes, data.filename)
            nombre_procesamiento = data.filename.rsplit('.', 1)[0] + '.pdf'
        else:
            if not validar_pdf(file_bytes):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail="El archivo no es un PDF válido"
                )
            pdf_bytes = file_bytes
            nombre_procesamiento = data.filename

        resultado = await procesar_pdf_completo(pdf_bytes, nombre_procesamiento)
        
        if resultado["error"]:
            raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al procesar: {resultado['error']}")
        
        documentos_finales_individuales[data.filename] = resultado["documentos_finales"]
        
        docs_response = []
        for doc_final in resultado["documentos_finales"]:
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
                await cache_repo.guardar_documento(
                    archivo_hash=archivo_hash,
                    nombre_archivo=data.filename,
                    tipo_operacion="procesar",
                    total_documentos_segmentados=len(docs_response),
                    resultado={"documentos": [doc.model_dump() for doc in docs_response]}
                )
            except Exception as e:
                logger.warning(f"Error guardando en caché: {e}")

        return ProcesamientoIndividualResponse(
            archivo_origen=data.filename,
            total_documentos_segmentados=len(docs_response),
            documentos=docs_response,
            cache_info=cache_info
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al procesar documento: {str(e)}")


documentos_router = Router(
    path="/documentos",
    route_handlers=[clasificar_documento_individual, procesar_documento_individual],
    tags=["Documentos"]
)
