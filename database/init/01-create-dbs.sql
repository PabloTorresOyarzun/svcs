-- 1. Base de datos legacy
CREATE DATABASE legacy;

-- Conectamos a desarrollo para crear los esquemas allí
\connect desarrollo

-- 2. Crear Esquemas para organizar las APIs
-- No creamos usuarios, solo las "carpetas" lógicas
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS parser_cache;

-- El usuario admin tiene acceso total por defecto, no se requieren GRANTS extra.