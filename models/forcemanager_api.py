# models/forcemanager_api.py

import requests
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

class ForceManagerAPI(models.AbstractModel):
    _name = 'forcemanager.api'
    _description = 'ForceManager API Wrapper (v4)'

    @api.model
    def _authenticate(self):
        """
        Obtiene el token con username/password en ForceManager v4.
        Guarda el token en ir.config_parameter para reutilizarlo.
        """
        api_user = self.env['ir.config_parameter'].sudo().get_param('forcemanager_integration.api_user')
        api_password = self.env['ir.config_parameter'].sudo().get_param('forcemanager_integration.api_password')
        base_url_login = self.env['ir.config_parameter'].sudo().get_param('forcemanager_integration.base_url_login')

        if not base_url_login:
            base_url_login = f"{self._get_base_url()}/login"

        if not api_user or not api_password:
            _logger.error("No se encontraron 'api_user' o 'api_password' en ir.config_parameter.")
            return

        payload = {
            'username': api_user,
            'password': api_password,
        }

        _logger.info(f"Iniciando solicitud de token a ForceManager. URL: {base_url_login}")
        try:
            response = requests.post(base_url_login, json=payload)
            _logger.info(f"HTTP {response.status_code}, respuesta: {response.text}")
            response.raise_for_status()

            data = response.json()
            token = data.get('token')
            if token:
                self.env['ir.config_parameter'].sudo().set_param(
                    'forcemanager_integration.access_token',
                    token
                )
                _logger.info("Token obtenido y guardado en ir.config_parameter.")
            else:
                _logger.warning(f"No se encontró 'token' en la respuesta: {data}")
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al autenticar en ForceManager: {e}")

    @api.model
    def _get_base_url(self):
        """
        Retorna la URL base v4. Ej: https://api.forcemanager.com/api/v4
        """
        return self.env['ir.config_parameter'].sudo().get_param(
            'forcemanager_integration.base_url',
            'https://api.forcemanager.com/api/v4'
        )

    @api.model
    def _get_access_token(self):
        """
        Retorna el token; si no existe, intenta autenticarse.
        """
        token = self.env['ir.config_parameter'].sudo().get_param('forcemanager_integration.access_token')
        if not token:
            self._authenticate()
            token = self.env['ir.config_parameter'].sudo().get_param('forcemanager_integration.access_token')
        return token

    @api.model
    def _perform_request(self, endpoint, method='GET', payload=None, custom_headers=None):
        """
        Ejecuta una petición HTTP a ForceManager v4 con 'X-Session-Key' en headers.
        endpoint p.ej. 'accounts', 'contacts', 'products', 'opportunities'.
        
        1) Obtiene el token
        2) Hace la petición con las cabeceras base + custom_headers
        3) Si recibe 401 => reautentica y reintenta 1 vez.
        """
        base_url = self._get_base_url().rstrip('/')
        url = f"{base_url}/{endpoint.lstrip('/')}"

        def do_request():
            """Pequeña función interna para no duplicar código."""
            token_now = self._get_access_token()
            headers = {
                'Content-Type': 'application/json',
                'Accept': '*/*',
                'X-Session-Key': token_now
            }
            # Si nos pasan cabeceras personalizadas (p.ej. {'Count': '9999'}), las añadimos
            if custom_headers:
                headers.update(custom_headers)

            _logger.info(f"Haciendo {method} a {url}, payload={payload}, headers={headers}")
            if method == 'GET':
                return requests.get(url, headers=headers, params=payload)
            elif method == 'POST':
                return requests.post(url, headers=headers, json=payload)
            elif method == 'PUT':
                return requests.put(url, headers=headers, json=payload)
            elif method == 'DELETE':
                return requests.delete(url, headers=headers)
            else:
                raise ValueError("Método HTTP no soportado")

        # 1) Primer intento
        resp = do_request()
        _logger.info(f"Respuesta ForceManager: {resp.status_code}, {resp.text}")

        if resp.status_code == 401:
            # 2) Reautenticar y reintentar UNA vez
            _logger.warning("Token caducado (401). Reautenticando y reintentando la petición.")
            self._authenticate()
            resp = do_request()  # segundo intento
            _logger.info(f"Respuesta ForceManager (2° intento): {resp.status_code}, {resp.text}")
        
        try:
            resp.raise_for_status()  # si sigue fallando, levantará excepción
            # Devuelve JSON (puede ser dict o lista)
            return resp.json() if resp.text else {}
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error en la petición ForceManager API: {e}")
            return {}

    # -------------------------------------------------------------------------
    # Última sincronización
    # -------------------------------------------------------------------------
    @api.model
    def get_last_sync_date(self, entity):
        """
        Lee la fecha de última sincronización (accounts, contacts, products, opportunities).
        """
        param_name = f"forcemanager_integration.{entity}_last_sync"
        date_str = self.env['ir.config_parameter'].sudo().get_param(param_name)
        if date_str:
            return fields.Datetime.from_string(date_str)
        return False

    @api.model
    def set_last_sync_date(self, entity, date_value=False):
        """
        Guarda la fecha de última sincronización en ir.config_parameter.
        """
        param_name = f"forcemanager_integration.{entity}_last_sync"
        if not date_value:
            date_value = fields.Datetime.now()
        self.env['ir.config_parameter'].sudo().set_param(
            param_name,
            fields.Datetime.to_string(date_value)
        )
        return True
