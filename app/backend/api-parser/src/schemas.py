from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class DocumentoSimplificado(BaseModel):
    nombre: str
    estado: str
    fecha_recepcion: str


class Usuarios(BaseModel):
    pedidor: Optional[List[str]] = None
    jefe_operaciones: Optional[List[str]] = None


class ConsultaResponse(BaseModel):
    codigo_despacho: str
    id_interno: str
    cliente: str
    estado: str
    tipo: str
    total_documentos: int
    documentos: List[DocumentoSimplificado]
    usuarios: Usuarios


class Alerta(BaseModel):
    pagina: int
    tipo: str
    descripcion: str


class DocumentoFinal(BaseModel):
    archivo_origen: str
    nombre_salida: str
    tipo: str
    paginas: List[int]
    alertas: Optional[List[Alerta]] = None
    datos_extraidos: Optional[Dict[str, Any]] = None


class CacheInfo(BaseModel):
    desde_cache: bool
    hash_documentos: Optional[str] = None
    fecha_cache: Optional[str] = None
    hay_cambios: Optional[bool] = None


class ProcesamientoResponse(BaseModel):
    codigo_despacho: str
    cliente: str
    estado: str
    tipo: str
    total_documentos_segmentados: int
    documentos: List[DocumentoFinal]
    cache_info: Optional[CacheInfo] = None


class ProcesamientoIndividualResponse(BaseModel):
    archivo_origen: str
    total_documentos_segmentados: int
    documentos: List[DocumentoFinal]
    cache_info: Optional[CacheInfo] = None


class TokenInfo(BaseModel):
    id: str
    name: str
    masked_token: str
    created_at: str
    created_by: str
    last_used: Optional[str] = None
    is_active: bool = True


class TokenCreateRequest(BaseModel):
    name: str


class TokenCreateResponse(BaseModel):
    id: str
    token: str
    name: str
    created_at: str
    message: str


class TokenDeleteResponse(BaseModel):
    success: bool
    message: str
