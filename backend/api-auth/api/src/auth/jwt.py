from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
import httpx
from functools import lru_cache
from typing import Any
import structlog

from src.config import get_settings

logger = structlog.get_logger()


class JWTValidationError(Exception):
    """Error en validacion de token JWT."""
    pass


class JWTValidator:
    """
    Validador de tokens JWT emitidos por Keycloak.
    Obtiene las claves publicas del endpoint JWKS.
    """

    def __init__(self):
        self.settings = get_settings()
        self._jwks: dict | None = None

    async def _fetch_jwks(self) -> dict:
        """Obtiene las claves publicas de Keycloak."""
        jwks_url = f"{self.settings.keycloak_issuer}/protocol/openid-connect/certs"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(jwks_url, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error("jwks_fetch_failed", error=str(e))
                raise JWTValidationError("Unable to fetch JWKS")

    async def get_jwks(self) -> dict:
        """Obtiene JWKS con cache."""
        if self._jwks is None:
            self._jwks = await self._fetch_jwks()
        return self._jwks

    def _get_signing_key(self, token: str, jwks: dict) -> dict:
        """Obtiene la clave de firma del token."""
        try:
            unverified_header = jwt.get_unverified_header(token)
        except JWTError as e:
            raise JWTValidationError(f"Invalid token header: {e}")

        kid = unverified_header.get("kid")
        if not kid:
            raise JWTValidationError("Token missing key ID")

        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key

        # Refrescar JWKS si no se encuentra la clave
        self._jwks = None
        raise JWTValidationError("Signing key not found")

    async def validate(self, token: str) -> dict[str, Any]:
        """
        Valida un token JWT y retorna el payload.

        Args:
            token: Token JWT a validar

        Returns:
            Payload decodificado del token

        Raises:
            JWTValidationError: Si el token es invalido
        """
        jwks = await self.get_jwks()

        try:
            signing_key = self._get_signing_key(token, jwks)
        except JWTValidationError:
            # Reintentar con JWKS refrescado
            jwks = await self._fetch_jwks()
            self._jwks = jwks
            signing_key = self._get_signing_key(token, jwks)

        try:
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self.settings.keycloak_client_id,
                issuer=self.settings.keycloak_issuer,
                options={
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
            return payload

        except ExpiredSignatureError:
            raise JWTValidationError("Token expired")
        except JWTError as e:
            logger.warning("jwt_validation_failed", error=str(e))
            raise JWTValidationError(f"Invalid token: {e}")


# Singleton
_jwt_validator: JWTValidator | None = None


def get_jwt_validator() -> JWTValidator:
    global _jwt_validator
    if _jwt_validator is None:
        _jwt_validator = JWTValidator()
    return _jwt_validator