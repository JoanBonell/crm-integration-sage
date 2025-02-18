def _sync_order_lines(self, order, fm_lines, is_new_order=False):
    """
    Crea/actualiza líneas del pedido usando el forcemanager_id del producto.
    Además, asigna en cada línea el campo forcemanager_line_id con el ID que
    ForceManager envía en cada línea.
    
    Lógica:
    - Si `is_new_order` es True, se compara el precio enviado por ForceManager (fm_price)
      con el list_price base del producto:
      * Si difieren, se fuerza que el precio unitario sea fm_price.
      * Si son iguales, se deja que Odoo calcule el precio según la tarifa.
    - Si no es un pedido nuevo, se deja price_unit en False para que Odoo aplique
      su lógica normal.
    """
    if order.state in ('sale', 'done', 'cancel'):
        _logger.info(
            "[_sync_order_lines] El pedido %d (FM ID=%s) está en estado '%s'; no se modifican las líneas.",
            order.id, order.forcemanager_id, order.state
        )
        return

    _logger.info("[_sync_order_lines] Eliminando líneas previas del pedido %d ...", order.id)
    order.order_line.unlink()

    # Detectar si la 'tarifa' del partner empieza por dígito
    pricelist = order.partner_id.property_product_pricelist
    pricelist_name = pricelist.name if pricelist else ""
    # Por defecto, asumimos "usar_precio_fm = True" si la tarifa no empieza por dígito
    usar_precio_fm = True
    if pricelist_name and pricelist_name[0].isdigit():
        usar_precio_fm = False

    _logger.info(
        "[_sync_order_lines] Procesando %d líneas para el pedido FM ID=%s (tarifa=%s, usar_precio_fm=%s, is_new_order=%s)...",
        len(fm_lines), order.forcemanager_id, pricelist_name, usar_precio_fm, is_new_order
    )

    for i, line_data in enumerate(fm_lines, start=1):
        # Obtenemos el id de la línea de ForceManager
        fm_line_id = line_data.get('id')
        
        # Obtenemos el id del producto desde la línea de FM
        fm_prod = line_data.get('productId')
        if isinstance(fm_prod, dict):
            fm_prod_id = fm_prod.get('id')
        else:
            fm_prod_id = fm_prod

        product_rec = self.env['product.product'].search(
            [('forcemanager_id', '=', fm_prod_id)],
            limit=1
        )
        if not product_rec:
            _logger.warning(
                "  Línea #%d => Producto FM ID=%s NO encontrado en Odoo. Se omite la línea.",
                i, fm_prod_id
            )
            continue

        qty = line_data.get('quantity', 1)
        fm_price = line_data.get('price', 0.0)
        description = line_data.get('productName') or product_rec.name or "(Sin descripción)"

        # Determinar price_unit
        price_unit = False  # Por defecto, que Odoo calcule según la tarifa
        if is_new_order:
            base_price = product_rec.list_price
            if not self._float_is_equal(base_price, fm_price):
                price_unit = fm_price
                _logger.info(
                    "  (Pedido nuevo) Forzamos price_unit=%s. [list_price=%s, FM=%s]",
                    fm_price, base_price, fm_price
                )
            else:
                _logger.info(
                    "  (Pedido nuevo) FM price %s == list_price %s => usaremos la tarifa Odoo (price_unit=False)",
                    fm_price, base_price
                )
        # Si no es un pedido nuevo, se deja price_unit=False para que Odoo calcule
        if not usar_precio_fm:
            price_unit = False

        _logger.info(
            "  Línea #%d => productName='%s', qty=%s, fm_price=%s => price_unit=%s",
            i, description, qty, fm_price, price_unit
        )

        line_vals = {
            'order_id': order.id,
            'product_id': product_rec.id,
            'product_uom_qty': qty,
            'name': description,
        }
        if price_unit is not False:
            line_vals['price_unit'] = price_unit

        new_line = self.env['sale.order.line'].create(line_vals)
        # Asignar forcemanager_line_id si se recibe en la línea de FM
        if fm_line_id:
            new_line.forcemanager_line_id = str(fm_line_id)
            _logger.info("  Línea #%d => forcemanager_line_id asignado: %s", i, new_line.forcemanager_line_id)
        else:
            _logger.info("  Línea #%d => No se encontró forcemanager_line_id en la línea de FM.", i)

        _logger.info(
            "  Línea #%d => Creada sale.order.line ID=%d para order_id=%d",
            i, new_line.id, order.id
        )

    _logger.info("[_sync_order_lines] Finalizado procesamiento de líneas para el pedido %d.", order.id)
