from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Configuracion centralizada de la aplicacion."""

    # Aplicacion
    app_env: str = "development"
    app_debug: bool = False
    app_secret_key: str

    # Keycloak
    keycloak_url: str
    keycloak_realm: str
    keycloak_client_id: str
    keycloak_client_secret: str
    keycloak_admin_user: str
    keycloak_admin_password: str

    # Base de datos de negocio
    business_db_host: str
    business_db_port: int = 5432
    business_db_user: str
    business_db_password: str
    business_db_name: str
    business_db_schema: str

    # Seguridad
    cors_origins: str = "http://localhost:3000"
    rate_limit_requests: int = 100
    rate_limit_period: int = 60

    @property
    def keycloak_issuer(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"

    @property
    def keycloak_admin_url(self) -> str:
        return f"{self.keycloak_url}/admin/realms/{self.keycloak_realm}"

    @property
    def business_db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.business_db_user}:{self.business_db_password}"
            f"@{self.business_db_host}:{self.business_db_port}/{self.business_db_name}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()