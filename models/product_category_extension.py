from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ProductCategory(models.Model):
    _inherit = 'product.category'

    forcemanager_id = fields.Char(
        string='ForceManager Category ID',
        copy=False,
        index=True,
        help="Guarda el ID de la categoría en ForceManager"
    )

    @api.model
    def sync_categories_to_forcemanager_on_init(self):
        _logger.info("[sync_categories_to_forcemanager_on_init] INICIO")

        # 1) OBTENER las categorías en ForceManager
        fm_categories = self.env['forcemanager.api']._perform_request(
            'productCategories',
            method='GET'
        )
        if not fm_categories:
            fm_categories = []
        elif not isinstance(fm_categories, list):
            fm_categories = fm_categories.get('results', [])

        _logger.info("Recibidas %d categorías desde ForceManager.", len(fm_categories))

        # 2) ELIMINAR EN FM las que NO existan en Odoo con b2b_available=True
        #
        #    Es decir, si en FM hay una categoría con id X pero en Odoo:
        #      - no existe ninguna categoría con forcemanager_id=X, o
        #      - sí existe, pero b2b_available=False,
        #    entonces la borramos de FM.
        #
        for fm_item in fm_categories:
            fm_id_str = str(fm_item.get('id'))
            # Buscamos en Odoo UNA categoría con forcemanager_id=fm_id_str y b2b_available=True
            cat_odoo = self.search([
                ('forcemanager_id', '=', fm_id_str),
                ('b2b_available', '=', True)
            ], limit=1)
            if not cat_odoo:
                _logger.info("Eliminando en ForceManager la categoría FM ID=%s (no existe o b2b_available=False en Odoo)",
                            fm_id_str)
                endpoint_delete = f"productCategories/{fm_id_str}"
                try:
                    self.env['forcemanager.api']._perform_request(endpoint_delete, method='DELETE')
                except Exception as e:
                    _logger.warning("Error intentando borrar la categoría FM ID=%s: %s", fm_id_str, e)

        # 3) CREAR/ACTUALIZAR EN FM únicamente las categorías de Odoo con b2b_available=True
        all_odoo_cats = self.search([('b2b_available', '=', True)])
        _logger.info("Analizando %d categorías de producto en Odoo (b2b_available=True).", len(all_odoo_cats))

        for cat in all_odoo_cats:
            payload_data = {
                "cLevel2": cat.id,
                "descriptionEN": cat.name or "Unnamed Category",  # Obligatorio para FM
                "descriptionES": cat.name or "Unnamed Category",
                "descriptionBR": "",
                "descriptionDE": "",
                "descriptionDK": "",
                "descriptionFR": "",
                "descriptionIT": "",
                "descriptionPT": "",
                "descriptionRU": "",
                "descriptionUS": "",
            }

            if not cat.forcemanager_id:
                # CREAR en ForceManager
                try:
                    response_create = self.env['forcemanager.api']._perform_request(
                        'productCategories',
                        method='POST',
                        payload=payload_data
                    )
                    if (response_create 
                            and isinstance(response_create, dict) 
                            and response_create.get('id')):
                        cat.write({'forcemanager_id': str(response_create['id'])})
                        _logger.info("Categoría '%s' creada en FM con ID=%s", cat.name, response_create['id'])
                except Exception as e:
                    _logger.warning("Error creando categoría '%s' en ForceManager: %s", cat.name, e)
            else:
                # ACTUALIZAR en ForceManager
                fm_id_str = cat.forcemanager_id
                payload_data.update({"id": int(fm_id_str)})
                endpoint_update = f"productCategories/{fm_id_str}"
                try:
                    self.env['forcemanager.api']._perform_request(
                        endpoint_update,
                        method='PUT',
                        payload=payload_data
                    )
                    _logger.info("Categoría '%s' (ID=%d) actualizada en FM ID=%s", cat.name, cat.id, fm_id_str)
                except Exception as e:
                    _logger.warning("Error actualizando categoría FM ID=%s: %s", fm_id_str, e)

        _logger.info("[sync_categories_to_forcemanager_on_init] FIN")

        
    def delete_all_categories_in_forcemanager(self):
        """
        Elimina TODAS las categorías existentes en ForceManager (¡cuidado!)
        Para casos de 'limpieza' o re-sync completo.
        """
        _logger.info("[delete_all_categories_in_forcemanager] Iniciando eliminación masiva en ForceManager.")
        # 1) Obtenemos la lista de categorías en ForceManager
        fm_categories = self.env['forcemanager.api']._perform_request('productCategories', method='GET')
        if not fm_categories:
            fm_categories = []
        elif not isinstance(fm_categories, list):
            fm_categories = fm_categories.get('results', [])

        _logger.info("Encontradas %d categorías en ForceManager. Eliminándolas una a una...", len(fm_categories))

        # 2) Por cada categoría, si tiene 'id', hacemos DELETE
        for item in fm_categories:
            fm_id = item.get('id')
            if fm_id:
                endpoint_delete = f"productCategories/{fm_id}"
                try:
                    self.env['forcemanager.api']._perform_request(endpoint_delete, method='DELETE')
                    _logger.info("Categoría FM ID=%s eliminada correctamente.", fm_id)
                except Exception as e:
                    _logger.warning("Error al eliminar la categoría FM ID=%s: %s", fm_id, e)

        _logger.info("[delete_all_categories_in_forcemanager] Finalizada la eliminación masiva.")

