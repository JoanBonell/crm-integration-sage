# ForceManager Integration

Este módulo integra Odoo con ForceManager, **cargando** las claves desde
`ir.config_parameter` en lugar de `.env` o `python-dotenv`.

## Configuración

Tras instalar el módulo:

1. Ir a **Ajustes** → **Técnico** → **Parámetros del sistema**.
2. Crear/Editar valores:
   - `forcemanager_integration.public_key` = ``
   - `forcemanager_integration.private_key` = ``
   - `forcemanager_integration.base_url` (opcional, por defecto `https://api.forcemanager.net`).
3. Activa los **cron jobs** (Programados) si quieres sincronizar de forma automática.
   - "ForceManager to Odoo Sync" (cada hora)
   - "Odoo to ForceManager Sync" (cada 2 horas)

## Uso

- **ForceManager → Odoo**: Los datos se recogen en `forcemanager_to_odoo_api.py`.
- **Odoo → ForceManager**: Los datos se envían en `odoo_to_forcemanager_api.py`.
- Cada entidad (partners, products, orders, opportunities) se sincroniza con su ID en ForceManager.

## Advertencias
- Ajusta el endpoint `/auth` y los payloads según la API real de ForceManager.
- El token se guarda en `forcemanager_integration.access_token` para no solicitarlo en cada request.
