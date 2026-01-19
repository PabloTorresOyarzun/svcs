from litestar import Router, post
from litestar.openapi.spec import Tag
from models.schemas import AgentQueryRequest, AgentQueryResponse
from agent.service import get_agent_service


@post(
    "/query",
    description="Procesa una pregunta en lenguaje natural y retorna una respuesta.",
    summary="Consulta al Agente",
    tags=["Agent"],
)
async def query_agent(data: AgentQueryRequest) -> AgentQueryResponse:
    """
    Endpoint principal para consultas al agente.
    
    - Si la pregunta requiere datos de la base de datos, genera y ejecuta SQL.
    - Si es una pregunta general, responde directamente.
    """
    service = get_agent_service()
    answer = await service.ask(data.query)
    return AgentQueryResponse(answer=answer)


agent_router = Router(
    path="/agent",
    route_handlers=[query_agent],
    tags=["Agent"],
)
