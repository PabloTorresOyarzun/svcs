import logging
from litestar import Litestar, get
from litestar.status_codes import HTTP_200_OK
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin, RedocRenderPlugin
from litestar.openapi.spec import Contact
from routers.agent import agent_router

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@get("/health", status_code=HTTP_200_OK, description="Health check endpoint")
async def health_check() -> dict:
    """Verifica el estado del servicio."""
    return {"status": "ok", "service": "api-agent"}


app = Litestar(
    route_handlers=[health_check, agent_router],
    openapi_config=OpenAPIConfig(
        title="API Agent - Agente Conversacional",
        version="1.0.0",
        description="""
API de agente conversacional para consultas en lenguaje natural a la base de datos de Aduanas.

## Funcionalidades
- **Consultas SQL**: Transforma preguntas en lenguaje natural a consultas SQL
- **Chat General**: Responde preguntas generales sobre el dominio aduanero

## Dominio
- DUS = Documento Único de Salida (Exportación)
- DIN = Declaración de Ingreso
- MIC/DTA = Manifiesto Internacional de Carga
- CRT = Carta de Porte por Carretera
        """,
        contact=Contact(name="API Agent Team"),
        path="/docs",
        render_plugins=[
            SwaggerRenderPlugin(),  # /docs/swagger
            RedocRenderPlugin(),    # /docs/redoc
        ],
    )
)
