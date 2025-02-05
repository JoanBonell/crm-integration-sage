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
        """
        Lógica de sincronización (Odoo => ForceManager) en la INSTALACIÓN del módulo.
        Pasos:
         1) Leer todas las categorías de FM (GET /productCategories).
         2) Eliminar en FM las que NO existan en Odoo.
         3) Crear/actualizar en FM cada categoría de Odoo,
            incluyendo cLevel2 y descriptionES / descriptionEN (y el resto vacío).
        """
        _logger.info("[sync_categories_to_forcemanager_on_init] INICIO")

        # 1) OBTENER las categorías en ForceManager
        fm_categories = self.env['forcemanager.api']._perform_request(
            'productCategories',
            method='GET'
        )
        if not fm_categories:
            fm_categories = []
        elif not isinstance(fm_categories, list):
            # Si la API devolviera algo tipo {"results": [...]} en lugar de lista
            fm_categories = fm_categories.get('results', [])

        _logger.info("Recibidas %d categorías desde ForceManager.", len(fm_categories))

        # Para localizarlas rápido por 'id'
        fm_dict = {str(item['id']): item for item in fm_categories if item.get('id')}

        # 2) ELIMINAR EN FM las que NO existen en Odoo
        #    - Recorremos la lista de fm_categories
        #    - Si no hay en Odoo ninguna con forcemanager_id=item['id'], se hace DELETE
        for fm_item in fm_categories:
            fm_id_str = str(fm_item.get('id'))
            # Buscar en Odoo
            cat_odoo = self.search([('forcemanager_id', '=', fm_id_str)], limit=1)
            if not cat_odoo:
                # Significa que en Odoo no existe => borrar en FM
                _logger.info("Eliminando en ForceManager la categoría FM ID=%s (no existe en Odoo)", fm_id_str)
                endpoint_delete = f"productCategories/{fm_id_str}"
                try:
                    self.env['forcemanager.api']._perform_request(endpoint_delete, method='DELETE')
                except Exception as e:
                    _logger.warning("Error intentando borrar la categoría FM ID=%s: %s", fm_id_str, e)

        # 3) RECORRER TODAS LAS CATEGORÍAS DE ODOO y crear/actualizar en FM
        all_odoo_cats = self.search([])
        _logger.info("Analizando %d categorías de producto en Odoo.", len(all_odoo_cats))

        for cat in all_odoo_cats:
            # Preparar las "descriptions" requeridas por ForceManager
            # ForceManager requiere descriptionEN (obligatorio), y sugiere los demás.
            # Ponemos cLevel2 = cat.id, descriptionES y descriptionEN con cat.name
            # El resto lo dejamos vacío.
            payload_data = {
                "cLevel2": cat.id,
                "descriptionEN": cat.name or "Unnamed Category",  # Obligatorio
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
                # CREAR en ForceManager => POST /productCategories
                # Además del 'payload_data', ForceManager podría requerir otros campos:
                # e.g. "extId", etc. Ajusta según su documentación.
                try:
                    response_create = self.env['forcemanager.api']._perform_request(
                        'productCategories',
                        method='POST',
                        payload=payload_data
                    )
                    if (response_create 
                            and isinstance(response_create, dict) 
                            and response_create.get('id')):
                        cat.write({
                            'forcemanager_id': str(response_create['id'])
                        })
                        _logger.info("Categoría '%s' creada en FM con ID=%s", cat.name, response_create['id'])
                except Exception as e:
                    _logger.warning("Error creando categoría '%s' en ForceManager: %s", cat.name, e)
            else:
                # ACTUALIZAR en ForceManager => PUT /productCategories/<forcemanager_id>
                fm_id_str = cat.forcemanager_id
                # ForceManager solicita "id" en el body para la actualización,
                # con un int (asumiendo que forcemanager_id es convertible a int).
                payload_data.update({
                    "id": int(fm_id_str),
                })
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

