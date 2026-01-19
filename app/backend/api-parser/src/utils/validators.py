import os
import fitz
import io
import pandas as pd
from PIL import Image
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_413_REQUEST_ENTITY_TOO_LARGE

from config.settings import get_settings

settings = get_settings()

def validar_pdf(file_bytes: bytes) -> bool:
    """Valida que los bytes sean un PDF válido."""
    if not file_bytes.startswith(b'%PDF'):
        return False
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        doc.close()
        return True
    except Exception:
        return False


def validar_excel(file_bytes: bytes, nombre_archivo: str) -> bool:
    """Valida que los bytes sean un archivo Excel válido."""
    extension = os.path.splitext(nombre_archivo.lower())[1]
    
    if extension in ['.xlsx', '.xlsm', '.xltx', '.xltm']:
        if not file_bytes.startswith(b'PK\x03\x04'):
            return False
    elif extension in ['.xls', '.xlsb']:
        if not file_bytes.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'):
            return False
    
    try:
        engine = 'xlrd' if extension == '.xls' else 'openpyxl'
        pd.read_excel(io.BytesIO(file_bytes), engine=engine, nrows=0)
        return True
    except Exception:
        return False


def validar_tamano_archivo(file_bytes: bytes) -> None:
    """Valida que el archivo no exceda el tamaño máximo."""
    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo excede el tamaño máximo de {settings.MAX_FILE_SIZE_MB}MB"
        )


def es_archivo_excel(nombre_archivo: str) -> bool:
    """Verifica si un archivo es Excel basándose en su extensión."""
    extensiones_excel = ['.xls', '.xlsx', '.xlsm', '.xlsb', '.xltx', '.xltm']
    extension = os.path.splitext(nombre_archivo.lower())[1]
    return extension in extensiones_excel


def es_archivo_imagen(nombre_archivo: str) -> bool:
    """Verifica si un archivo es una imagen basándose en su extensión."""
    extensiones_imagen = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp']
    extension = os.path.splitext(nombre_archivo.lower())[1]
    return extension in extensiones_imagen


def validar_imagen(file_bytes: bytes, nombre_archivo: str) -> bool:
    """Valida que los bytes sean una imagen válida."""
    try:
        imagen = Image.open(io.BytesIO(file_bytes))
        imagen.verify()
        return True
    except Exception:
        return False
