from litestar import Litestar, get
from litestar.openapi import OpenAPIConfig
from litestar.openapi.spec import Contact, License, Server
from litestar.config.cors import CORSConfig
from contextlib import asynccontextmanager
import structlog

from src.config import get_settings
from src.middleware.security import (
    security_headers_middleware,
    rate_limit_middleware,
    audit_log_middleware,
)
from src.users.controller import UserController
from src.roles.controller import RoleController, UserRoleController
from src.groups.controller import GroupController, UserGroupController
from src.sync.user_sync import get_user_sync_service

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: Litestar):
    """
    Ciclo de vida de la aplicacion.
    Inicializa recursos al arrancar y los libera al cerrar.
    """
    settings = get_settings()

    # Startup
    logger.info("application_starting", env=settings.app_env)

    # Asegurar que la tabla de usuarios existe en la base de negocio
    sync_service = get_user_sync_service()
    await sync_service.ensure_table_exists()

    yield

    # Shutdown
    await sync_service.close()
    logger.info("application_stopped")


@get(path="/health", exclude_from_auth=True, include_in_schema=False)
async def health_check() -> dict:
    """Endpoint de health check para orquestacion."""
    return {"status": "healthy"}


@get(path="/", exclude_from_auth=True, include_in_schema=False)
async def root() -> dict:
    """Redirige a la documentacion."""
    return {"message": "Auth API", "docs": "/auth/swagger"}


def create_app() -> Litestar:
    """Factory de la aplicacion."""
    settings = get_settings()

    # Configuracion CORS
    cors_config = CORSConfig(
        allow_origins=settings.cors_origins_list,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=True,
        max_age=600,
    )

    # Configuracion OpenAPI/Swagger
    openapi_config = OpenAPIConfig(
        title="Auth API - Sistema de Gestion Aduanera",
        version="1.0.0",
        description="""
API de autenticacion y gestion de usuarios para el Sistema de Gestion Aduanera.

## Funcionalidades

- **Gestion de usuarios**: CRUD completo de usuarios
- **Gestion de roles**: CRUD de roles y asignacion a usuarios
- **Gestion de grupos**: CRUD de grupos, subgrupos y asignacion de usuarios
- **Sincronizacion**: Proyeccion de usuarios en base de datos de negocio
- **Seguridad**: Headers OWASP, rate limiting, logging de auditoria

## Autenticacion

Esta API requiere tokens JWT emitidos por Keycloak.
Incluir el token en el header `Authorization: Bearer <token>`.
        """,
        contact=Contact(
            name="Equipo de Desarrollo",
            email="dev@agencia.cl",
        ),
        license=License(
            name="Privado",
            identifier="UNLICENSED",
        ),
        servers=[
            Server(url="http://localhost:8000", description="Desarrollo local"),
        ],
        path="/auth",
    )

    return Litestar(
        route_handlers=[
            root,
            health_check,
            UserController,
            RoleController,
            UserRoleController,
            GroupController,
            UserGroupController,
        ],
        middleware=[
            audit_log_middleware,
            rate_limit_middleware,
            security_headers_middleware,
        ],
        cors_config=cors_config,
        openapi_config=openapi_config,
        lifespan=[lifespan],
        debug=settings.app_debug,
    )


app = create_app()