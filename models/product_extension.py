# models/product_extension.py

from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    forcemanager_id = fields.Char(
        string='ForceManager ID',
        copy=False,
        index=True
    )
    synced_with_forcemanager = fields.Boolean(
        string='Synced with ForceManager',
        default=False
    )

        
    @api.model
    def export_all_products_to_forcemanager(self):
        """
        Envía TODOS los productos de Odoo a ForceManager.
        - Si forcemanager_id está vacío => POST /products
        - Si forcemanager_id existe => PUT /products/{id}
        - Incluye categoryId como ENTERO si 'categ_id.forcemanager_id' está disponible (no un objeto).
        """
        _logger.info("[export_all_products_to_forcemanager] Iniciando exportación masiva Odoo→FM de productos.")
        all_products = self.search([])
        _logger.info("Se han encontrado %d productos en Odoo para exportar.", len(all_products))

        for product in all_products:
            # 1) Determinar la categoryId como ENTERO
            cat_id_int = False
            if product.categ_id and product.categ_id.forcemanager_id:
                try:
                    cat_id_int = int(product.categ_id.forcemanager_id)
                except ValueError:
                    cat_id_int = False

            # 2) Construir payload
            # ForceManager usa "model" para el nombre, "price" para list_price, etc.
            data = {
                "model": product.name or "(Sin nombre)",
                "description": product.description_sale or "",
                "price": product.list_price or 0.0,
                "cost": product.standard_price or 0.0,
                # Enviar categoryId como entero
            }
            if cat_id_int:
                data["categoryId"] = cat_id_int
            
            # (Si deseas enviar stock, añade "stock": product.qty_available, etc.)

            if not product.forcemanager_id:
                # POST => crear producto en ForceManager
                try:
                    _logger.info(
                        "[export_all_products_to_forcemanager] Creando en FM el producto ID=%d '%s'.",
                        product.id, product.name
                    )
                    resp = self.env['forcemanager.api']._perform_request(
                        "products", method="POST", payload=data
                    )
                    # Si se creó correctamente y devuelven un ID
                    if resp and isinstance(resp, dict) and resp.get('id'):
                        product.forcemanager_id = str(resp['id'])
                        product.synced_with_forcemanager = True
                except Exception as e:
                    _logger.warning("Error creando producto '%s' en FM: %s", product.name, e)

            else:
                # PUT => actualizar producto existente en ForceManager
                fm_id_str = product.forcemanager_id
                try:
                    data["id"] = int(fm_id_str)  # ForceManager pide "id" en el payload
                except ValueError:
                    _logger.warning("forcemanager_id='%s' no es un entero válido, se omite.", fm_id_str)
                    continue

                endpoint = f"products/{fm_id_str}"
                try:
                    _logger.info(
                        "[export_all_products_to_forcemanager] Actualizando FM product.template ID=%d, FM ID=%s", 
                        product.id, fm_id_str
                    )
                    resp = self.env['forcemanager.api']._perform_request(endpoint, method="PUT", payload=data)
                    product.synced_with_forcemanager = True
                except Exception as e:
                    _logger.warning("Error actualizando producto ID=%d (FM ID=%s): %s", product.id, fm_id_str, e)

        _logger.info("[export_all_products_to_forcemanager] Finalizada exportación de productos Odoo→FM.")
