import asyncio
import time
import os
import fitz
import logging
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor

from config.settings import get_settings, calcular_timeout_calidad
from middleware import suprimir_prints
from services.quality_engine import paso_1_analizar_documento, paso_2_corregir_rotacion
from services.classification_engine import clasificar_documento_completo, segmentar_pdf
from services.azure_service import verificar_modelo_entrenado, extraer_datos_con_modelo

logger = logging.getLogger(__name__)
settings = get_settings()

# Mapeo de tipos de documento al modelo (todos usan el mismo modelo master)
# Needs to be same as original
CUSTOM_MODEL_ID = "master-01-alpha"
DOCUMENT_TYPE_TO_MODEL = {
    "FACTURA_COMERCIAL": CUSTOM_MODEL_ID,
    "DOCUMENTO_TRANSPORTE": CUSTOM_MODEL_ID,
    "CERTIFICADO_ORIGEN": CUSTOM_MODEL_ID,
    "LISTA_EMBALAJE": CUSTOM_MODEL_ID,
    "CERTIFICADO_SANITARIO": CUSTOM_MODEL_ID,
    "POLIZA_SEGURO": CUSTOM_MODEL_ID,
    "UNKNOWN_DOCUMENT": None
}

executor = ThreadPoolExecutor(max_workers=min(settings.EXECUTOR_MAX_WORKERS, (os.cpu_count() or 1) * 4))

def _procesar_calidad_sync(pdf_bytes: bytes) -> tuple:
    """Función síncrona interna para procesamiento de calidad."""
    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    with suprimir_prints():
        resultados_paso_1 = paso_1_analizar_documento(pdf_doc)
        paginas_corregidas = paso_2_corregir_rotacion(pdf_doc, resultados_paso_1)
    
    if paginas_corregidas > 0:
        pdf_bytes = pdf_doc.tobytes()
    
    pdf_doc.close()
    return pdf_bytes, resultados_paso_1


async def clasificar_pdf_completo(pdf_bytes: bytes, nombre_archivo: str) -> Dict[str, Any]:
    """Flujo de clasificación de PDF (sin extracción de datos)."""
    timeout_calidad = 0
    try:
        pdf_doc_temp = fitz.open(stream=pdf_bytes, filetype="pdf")
        num_paginas = len(pdf_doc_temp)
        pdf_doc_temp.close()

        timeout_calidad = calcular_timeout_calidad(num_paginas)

        logger.info(f"Iniciando procesamiento de calidad para {nombre_archivo} ({num_paginas} páginas, timeout={timeout_calidad}s)")
        start_time = time.time()

        loop = asyncio.get_event_loop()
        pdf_bytes, resultados_paso_1 = await asyncio.wait_for(
            loop.run_in_executor(
                executor,
                _procesar_calidad_sync,
                pdf_bytes
            ),
            timeout=timeout_calidad
        )

        elapsed_time = time.time() - start_time
        logger.info(f"Procesamiento de calidad completado para {nombre_archivo} en {elapsed_time:.2f}s")

        clasificaciones = await clasificar_documento_completo(pdf_bytes)

        logger.info(f"Iniciando segmentación para {nombre_archivo}")
        start_time = time.time()

        documentos_segmentados = await loop.run_in_executor(
            executor,
            segmentar_pdf,
            pdf_bytes,
            clasificaciones
        )

        elapsed_time = time.time() - start_time
        logger.info(f"Segmentación completada para {nombre_archivo} en {elapsed_time:.2f}s - {len(documentos_segmentados)} documentos")

        alertas_por_documento = {}
        for resultado in resultados_paso_1:
            alertas = []

            if resultado['escaneada']:
                if 'INCLINADA' in resultado['orientacion']:
                    alertas.append({
                        "pagina": resultado['pagina'],
                        "tipo": "inclinado",
                        "descripcion": f"Página escaneada {resultado['orientacion']}"
                    })
                elif resultado['orientacion'] not in ['NORMAL', 'SIN TEXTO', 'SIN IMAGEN']:
                    alertas.append({
                        "pagina": resultado['pagina'],
                        "tipo": "escaneado",
                        "descripcion": f"Página escaneada: {resultado['orientacion']}"
                    })

            if resultado['rotacion_formal'] != 0:
                alertas.append({
                    "pagina": resultado['pagina'],
                    "tipo": "rotado",
                    "descripcion": f"Rotación de {resultado['rotacion_formal']}° corregida"
                })

            if not resultado['escaneada'] and resultado['orientacion'] == 'ROTADA':
                alertas.append({
                    "pagina": resultado['pagina'],
                    "tipo": "rotado",
                    "descripcion": "Texto vertical corregido"
                })

            if alertas:
                alertas_por_documento[resultado['pagina']] = alertas

        documentos_finales = []
        for idx, doc_seg in enumerate(documentos_segmentados):
            alertas_segmento = []
            for pagina in doc_seg['paginas']:
                if pagina in alertas_por_documento:
                    alertas_segmento.extend(alertas_por_documento[pagina])

            nombre_salida = f"{nombre_archivo.replace('.pdf', '')}_{doc_seg['tipo']}_{idx+1}.pdf"

            documentos_finales.append({
                "archivo_origen": nombre_archivo,
                "nombre_salida": nombre_salida,
                "tipo": doc_seg['tipo'],
                "paginas": doc_seg['paginas'],
                "pdf_bytes": doc_seg['pdf_bytes'],
                "alertas": alertas_segmento if alertas_segmento else None,
                "datos_extraidos": None
            })

        return {
            "documentos_finales": documentos_finales,
            "clasificaciones": clasificaciones,
            "error": None
        }

    except asyncio.TimeoutError:
        logger.error(f"Timeout en procesamiento de calidad para {nombre_archivo}")
        return {
            "documentos_finales": [],
            "clasificaciones": [],
            "error": f"Timeout en procesamiento de calidad ({timeout_calidad}s)"
        }
    except Exception as e:
        logger.error(f"Error en clasificar_pdf_completo para {nombre_archivo}: {str(e)}")
        return {
            "documentos_finales": [],
            "clasificaciones": [],
            "error": str(e)
        }


async def procesar_pdf_completo(pdf_bytes: bytes, nombre_archivo: str) -> Dict[str, Any]:
    """Flujo completo de procesamiento de PDF."""
    timeout_calidad = 0
    try:
        pdf_doc_temp = fitz.open(stream=pdf_bytes, filetype="pdf")
        num_paginas = len(pdf_doc_temp)
        pdf_doc_temp.close()

        timeout_calidad = calcular_timeout_calidad(num_paginas)

        logger.info(f"Iniciando procesamiento de calidad para {nombre_archivo} ({num_paginas} páginas, timeout={timeout_calidad}s)")
        start_time = time.time()

        loop = asyncio.get_event_loop()
        pdf_bytes, resultados_paso_1 = await asyncio.wait_for(
            loop.run_in_executor(
                executor,
                _procesar_calidad_sync,
                pdf_bytes
            ),
            timeout=timeout_calidad
        )

        elapsed_time = time.time() - start_time
        logger.info(f"Procesamiento de calidad completado para {nombre_archivo} en {elapsed_time:.2f}s")

        clasificaciones = await clasificar_documento_completo(pdf_bytes)

        logger.info(f"Iniciando segmentación para {nombre_archivo}")
        start_time = time.time()

        documentos_segmentados = await loop.run_in_executor(
            executor,
            segmentar_pdf,
            pdf_bytes,
            clasificaciones
        )

        elapsed_time = time.time() - start_time
        logger.info(f"Segmentación completada para {nombre_archivo} en {elapsed_time:.2f}s - {len(documentos_segmentados)} documentos")

        alertas_por_documento = {}
        for resultado in resultados_paso_1:
            alertas = []

            if resultado['escaneada']:
                if 'INCLINADA' in resultado['orientacion']:
                    alertas.append({
                        "pagina": resultado['pagina'],
                        "tipo": "inclinado",
                        "descripcion": f"Página escaneada {resultado['orientacion']}"
                    })
                elif resultado['orientacion'] not in ['NORMAL', 'SIN TEXTO', 'SIN IMAGEN']:
                    alertas.append({
                        "pagina": resultado['pagina'],
                        "tipo": "escaneado",
                        "descripcion": f"Página escaneada: {resultado['orientacion']}"
                    })

            if resultado['rotacion_formal'] != 0:
                alertas.append({
                    "pagina": resultado['pagina'],
                    "tipo": "rotado",
                    "descripcion": f"Rotación de {resultado['rotacion_formal']}° corregida"
                })

            if not resultado['escaneada'] and resultado['orientacion'] == 'ROTADA':
                alertas.append({
                    "pagina": resultado['pagina'],
                    "tipo": "rotado",
                    "descripcion": "Texto vertical corregido"
                })

            if alertas:
                alertas_por_documento[resultado['pagina']] = alertas

        documentos_finales = []
        for idx, doc_seg in enumerate(documentos_segmentados):
            alertas_segmento = []
            for pagina in doc_seg['paginas']:
                if pagina in alertas_por_documento:
                    alertas_segmento.extend(alertas_por_documento[pagina])

            nombre_salida = f"{nombre_archivo.replace('.pdf', '')}_{doc_seg['tipo']}_{idx+1}.pdf"

            tipo_documento = doc_seg['tipo']
            model_id = DOCUMENT_TYPE_TO_MODEL.get(tipo_documento)

            datos_extraidos = None

            if model_id:
                try:
                    modelo_entrenado = await verificar_modelo_entrenado(model_id)

                    if modelo_entrenado:
                        datos_extraidos = await extraer_datos_con_modelo(
                            doc_seg['pdf_bytes'],
                            model_id
                        )
                except Exception as e:
                    logger.error(f"Error extrayendo datos: {str(e)}")
                    datos_extraidos = None

            documentos_finales.append({
                "archivo_origen": nombre_archivo,
                "nombre_salida": nombre_salida,
                "tipo": doc_seg['tipo'],
                "paginas": doc_seg['paginas'],
                "pdf_bytes": doc_seg['pdf_bytes'],
                "alertas": alertas_segmento if alertas_segmento else None,
                "datos_extraidos": datos_extraidos
            })

        return {
            "documentos_finales": documentos_finales,
            "clasificaciones": clasificaciones,
            "error": None
        }

    except asyncio.TimeoutError:
        logger.error(f"Timeout en procesamiento de calidad para {nombre_archivo}")
        return {
            "documentos_finales": [],
            "clasificaciones": [],
            "error": f"Timeout en procesamiento de calidad ({timeout_calidad}s)"
        }
    except Exception as e:
        logger.error(f"Error en procesar_pdf_completo para {nombre_archivo}: {str(e)}")
        return {
            "documentos_finales": [],
            "clasificaciones": [],
            "error": str(e)
        }


def serializar_documentos_para_cache(documentos: List[Dict]) -> List[Dict]:
    """Prepara documentos para almacenamiento en caché (sin pdf_bytes)."""
    return [
        {
            "archivo_origen": doc["archivo_origen"],
            "nombre_salida": doc["nombre_salida"],
            "tipo": doc["tipo"],
            "paginas": doc["paginas"],
            "alertas": doc.get("alertas"),
            "datos_extraidos": doc.get("datos_extraidos")
        }
        for doc in documentos
    ]
