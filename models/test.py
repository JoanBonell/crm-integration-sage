def _sync_order_lines(self, order, fm_lines):
    """
    Crea/actualiza líneas del pedido usando el forcemanager_id del producto.
    Si el pedido ya está confirmado (state='sale' o 'done') o cancelado (state='cancel'),
    NO se toca ninguna línea.
    """
    if order.state in ('sale', 'done', 'cancel'):
        _logger.info(
            "[_sync_order_lines] El pedido %d (FM ID=%s) está en estado '%s'; no se modifican las líneas.",
            order.id, order.forcemanager_id, order.state
        )
        return

    _logger.info("[_sync_order_lines] Eliminando líneas previas del pedido %d ...", order.id)
    order.order_line.unlink()

    # 1) Verificamos la tarifa del partner
    pricelist = order.partner_id.property_product_pricelist
    pricelist_name = pricelist.name if pricelist else ""
    # Comprobar si *no* empieza por dígito
    # Ejemplo sencillo: si la primera letra NO es un dígito => usaremos precio de ForceManager
    usar_precio_fm = True
    if pricelist_name and pricelist_name[0].isdigit():
        usar_precio_fm = False

    _logger.info(
        "[_sync_order_lines] Procesando %d líneas para el pedido FM ID=%s (tarifa=%s, usar_precio_fm=%s)...",
        len(fm_lines), order.forcemanager_id, pricelist_name, usar_precio_fm
    )

    for i, line_data in enumerate(fm_lines, start=1):
        # Extraer productId
        fm_prod = line_data.get('productId')
        if isinstance(fm_prod, dict):
            fm_prod_id = fm_prod.get('id')
        else:
            fm_prod_id = fm_prod

        product_rec = self.env['product.product'].search(
            [('forcemanager_id', '=', fm_prod_id)], limit=1
        )
        if not product_rec:
            _logger.warning(
                "  Línea #%d => Producto FM ID=%s NO encontrado en Odoo. Se omite la línea.",
                i, fm_prod_id
            )
            continue

        qty = line_data.get('quantity', 1)
        description = line_data.get('productName') or product_rec.name or "Línea sin producto"

        # 2) Si la tarifa no empieza por dígito, forzamos el price_unit con el que venga de ForceManager
        # (puede que FM devuelva 'price' o 'price_unit', ajusta según tu JSON)
        fm_price = line_data.get('price_unit', 0.0)  # Ajusta la clave si en tu JSON se llama de otra forma
        price_unit = fm_price if usar_precio_fm else False

        _logger.info(
            "  Línea #%d => productName='%s', cantidad=%s, price_unit=%s (tarifa sin dígito? %s)",
            i, description, qty, fm_price, usar_precio_fm
        )

        line_vals = {
            'order_id': order.id,
            'product_id': product_rec.id,
            'product_uom_qty': qty,
            'name': description,
        }
        if usar_precio_fm:
            line_vals['price_unit'] = price_unit

        new_line = self.env['sale.order.line'].create(line_vals)
        _logger.info(
            "  Línea #%d => Creada sale.order.line ID=%d para order_id=%d",
            i, new_line.id, order.id
        )

    _logger.info("[_sync_order_lines] Finalizado procesamiento de líneas para el pedido %d.", order.id)
