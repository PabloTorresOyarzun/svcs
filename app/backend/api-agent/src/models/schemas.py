from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    """Solicitud de consulta al agente."""
    query: str = Field(..., description="Pregunta en lenguaje natural", examples=["¿Cuántos despachos hay?"])


class AgentQueryResponse(BaseModel):
    """Respuesta del agente."""
    answer: str = Field(..., description="Respuesta generada por el agente")
