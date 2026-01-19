import logging
from litestar import Litestar, get
from litestar.openapi import OpenAPIConfig
from litestar.openapi.spec import Components, SecurityScheme

from database.connection import db_manager
from routers.sgd import sgd_router
from routers.documentos import documentos_router
from routers.admin import admin_router, cache_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@get("/")
async def root() -> dict:
    return {"status": "online", "service": "API Docs", "azure_di": "cloud", "cache": "postgresql"}

async def on_startup():
    """Inicializa conexiones al iniciar la aplicación."""
    try:
        await db_manager.initialize()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error inicializando base de datos: {e}")

async def on_shutdown():
    """Cierra conexiones al detener la aplicación."""
    await db_manager.close()
    logger.info("Conexiones cerradas")

app = Litestar(
    route_handlers=[
        root,
        sgd_router,
        documentos_router,
        admin_router,
        cache_router,
    ],
    on_startup=[on_startup],
    on_shutdown=[on_shutdown],
    openapi_config=OpenAPIConfig(
        title="API Docs",
        version="2.1.0",
        components=Components(
            security_schemes={
                "BearerAuth": SecurityScheme(
                    type="http",
                    scheme="bearer",
                    bearer_format="JWT",
                    description="Token de autenticación API"
                )
            }
        ),
        security=[{"BearerAuth": []}]
    ),
    request_max_body_size=500 * 1024 * 1024,  # 500MB
)