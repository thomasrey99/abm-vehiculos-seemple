"""
Script de una sola vez para sacar el bearer token y la URL de tu instancia
activa directamente del ADK ya instalado, sin pelear con DevTools.

Uso:
    (con el venv de orchestrate/ activado)
    python get_orchestrate_token.py

Esto imprime:
    - El nombre del entorno activo (draft/live segun corresponda)
    - La URL base de la API
    - El bearer token para usar en curl / Postman contra la API de threads

Nota: usa las mismas rutas de config internas que usa el propio CLI de
`orchestrate`, asi que si tu version del ADK cambio esos nombres, este
script puede necesitar un ajuste minimo.
"""

from ibm_watsonx_orchestrate.cli.config import (
    Config,
    AUTH_CONFIG_FILE_FOLDER,
    AUTH_CONFIG_FILE,
    AUTH_SECTION_HEADER,
    AUTH_MCSP_TOKEN_OPT,
    CONTEXT_SECTION_HEADER,
    CONTEXT_ACTIVE_ENV_OPT,
    ENVIRONMENTS_SECTION_HEADER,
    ENV_WXO_URL_OPT,
)

cfg = Config()
auth_cfg = Config(AUTH_CONFIG_FILE_FOLDER, AUTH_CONFIG_FILE)

active_env = cfg.read(CONTEXT_SECTION_HEADER, CONTEXT_ACTIVE_ENV_OPT)
url = cfg.get(ENVIRONMENTS_SECTION_HEADER, active_env, ENV_WXO_URL_OPT)

auth_section = auth_cfg.get(AUTH_SECTION_HEADER) or {}
auth_data = auth_section.get(active_env, {})
token = auth_data.get(AUTH_MCSP_TOKEN_OPT)

print("Entorno activo:", active_env)
print("API URL:", url)
print("Bearer token:", token)