# forcemanager_integration/models/res_country.py

from odoo import models, fields, api

class ResCountry(models.Model):
    _inherit = 'res.country'

    forcemanager_id = fields.Integer(
        string='ForceManager Country ID',
        index=True,
        copy=False
    )

    @api.model
    def sync_countries_from_forcemanager(self):
        """
        Descarga la lista completa de países de ForceManager
        (endpoint /api/v4/countries)
        y los vincula con res.country en Odoo.
        
        Lógica:
         - Para cada país de ForceManager:
             1) Leer iso2 e id.
             2) Buscar un res.country con code = iso2
             3) Actualizar su forcemanager_id
             4) Si no existe, crearlo (opcional).
        """
        # Añadimos la cabecera 'Count' para que retorne más de 50 países
        all_countries = self.env['forcemanager.api']._perform_request(
            'countries',
            method='GET',
            custom_headers={'Count': '300'}  # Ajusta este valor según necesidad
        )
        if not all_countries or not isinstance(all_countries, list):
            return  # No hay datos o error en la API

        for item in all_countries:
            fm_id = item.get('id')    # p.ej. 4
            iso2 = item.get('iso2')   # p.ej. "ES"
            str_name = item.get('strName') or "Unnamed"

            if not iso2:
                # Si no hay iso2, no podemos buscar por 'code'
                continue

            # Buscamos el country en Odoo
            country = self.search([('code', '=', iso2)], limit=1)
            if country:
                # Actualizamos su forcemanager_id
                country.write({'forcemanager_id': fm_id})
            else:
                # Si no existe, lo creamos
                self.create({
                    'name': str_name,
                    'code': iso2,
                    'forcemanager_id': fm_id,
                })
