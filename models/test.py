def verificar_productos_forcemanager_sincronizados(self):
    """
    1) Descarga la lista actual de productos "vivos" en ForceManager (deleted=false).
    2) Para cada uno de ellos, verifica si corresponde con algo en Odoo:
       - Si NO existe en Odoo o su categoría no es b2b_available,
         se borra en FM (DELETE /products/<id>).
    """
    _logger.info("[verificar_productos_forcemanager_sincronizados] Iniciando verificación en ForceManager...")

    # Agregamos ?where=(deleted=false) para no recibir los ya eliminados
    endpoint_url = "products?where=(deleted=false)"
    fm_products = self.env['forcemanager.api']._perform_request(endpoint_url, method='GET')
    if not fm_products:
        fm_products = []
    elif not isinstance(fm_products, list):
        fm_products = fm_products.get('results', [])

    _logger.info("Se han encontrado %d productos NO borrados en ForceManager.", len(fm_products))

    # Procesar...
    for fm_prod in fm_products:
        fm_id = fm_prod.get('id')
        if not fm_id:
            continue
        # Busca el producto en Odoo
        product_odoo = self.env['product.template'].search([('forcemanager_id', '=', str(fm_id))], limit=1)
        if not product_odoo:
            # No existe => lo borramos en FM
            self._eliminar_producto_forcemanager(fm_id, reason="No existe en Odoo")
            continue

        # Comprobamos categoría
        categ = product_odoo.categ_id
        if not categ.b2b_available:
            self._eliminar_producto_forcemanager(fm_id, reason=f"Categ '{categ.name}' no es b2b_available")
            continue

        # Si hay otras validaciones, etc.

    _logger.info("[verificar_productos_forcemanager_sincronizados] Finalizada la verificación.")
