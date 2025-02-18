# models/odoo_to_forcemanager_api.py

import logging
from datetime import datetime
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class OdooToForceManagerAPI(models.TransientModel):
    _name = 'odoo.to.forcemanager'
    _description = 'Sync Odoo → ForceManager (accounts, contacts, products, opportunities, orders)'

    @api.model
    def action_sync_to_forcemanager(self):
        """
        Punto de entrada para enviar datos de Odoo a ForceManager.
        """
        _logger.info(">>> [OdooToForceManagerAPI] action_sync_to_forcemanager() START")

        # Llamamos solamente a sync_products(), por ejemplo.
        # (Descomenta las otras si quieres sincronizarlas)
        #self.sync_accounts()
        #self.sync_contacts()
        self.sync_products()
        #self.sync_opportunities()
        self.sync_orders()

        _logger.info("<<< [OdooToForceManagerAPI] action_sync_to_forcemanager() END")
        
        
     # -------------------------------------------------------------------------
    # ORDERS (sale.order)
    # -------------------------------------------------------------------------
    def sync_orders(self):
        """
        Envía pedidos (sale.order) de Odoo a ForceManager,
        **solo** aquellos que tengan al menos un producto con categ_id.b2b_available = True.
        """
        _logger.info("[sync_orders] Iniciando envío de 'orders' a FM.")
        last_sync_date = self._get_last_sync_date('orders')
        
        # Dominio básico (filtra por triple OR: write_date > last_sync, etc.)
        domain = self._build_domain_for_odoo2fm(last_sync_date)
        
        # Añadimos la condición de que en ALGUNA línea haya productos con b2b_available
        # => Se traduce a: ('order_line.product_id.categ_id.b2b_available', '=', True)
        domain.append(('order_line.product_id.categ_id.b2b_available', '=', True))

        orders = self.env['sale.order'].search(domain)
        if not orders:
            _logger.info("[sync_orders] No hay pedidos que enviar (dominio=%s).", domain)
            return

        _logger.info("[sync_orders] Encontrados %d pedidos. (dominio=%s)", len(orders), domain)

        to_create = orders.filtered(lambda o: not o.forcemanager_id)
        to_update = orders - to_create

        # =========== CREAR (POST) =========== 
        if to_create:
            for so in to_create:
                single_pl = self._prepare_single_order_payload(so, is_create=True)
                resp = self.env['forcemanager.api']._perform_request("sales", method='POST', payload=single_pl)
                if resp and isinstance(resp, dict) and resp.get('id'):
                    so.forcemanager_id = resp['id']
                so.synced_with_forcemanager = True

        # =========== ACTUALIZAR =========== 
        if to_update:
            payload_update = []
            for so in to_update:
                payload_update.append({
                    "guid": f"odoo_update_{so.id}",
                    "data": self._prepare_single_order_payload(so, is_create=False),
                })

            endpoint_update = "sales/bulk"
            if payload_update and self._has_bulk_endpoint(endpoint_update):
                resp = self.env['forcemanager.api']._perform_request(endpoint_update, method='PUT', payload=payload_update)
                self._process_bulk_update_response(resp, to_update)
            else:
                _logger.warning("[sync_orders] /sales/bulk (PUT) no disponible. Fallback 1x1.")
                for so in to_update:
                    single_pl = self._prepare_single_order_payload(so, is_create=False)
                    ep = f"sales/{so.forcemanager_id}"
                    self.env['forcemanager.api']._perform_request(ep, method='PUT', payload=single_pl)
                    so.synced_with_forcemanager = True

        self._update_last_sync_date('orders')
        _logger.info("[sync_orders] Finalizada la sincronización de pedidos.")





    def _prepare_single_order_payload(self, so, is_create=True):
        data = {}
        if not is_create and so.forcemanager_id:
            data['id'] = so.forcemanager_id

        fm_account_id = None
        if so.partner_id and so.partner_id.forcemanager_id:
            fm_account_id = {
                'id': so.partner_id.forcemanager_id,
                'value': so.partner_id.name
            }

        currency_val = {'value': so.currency_id.name} if so.currency_id else None

        # Comercial => fallback {id=95, 'value': 'Joan Bonell'}
        if so.user_id and so.user_id.forcemanager_id:
            fm_salesrep = {
                'id': so.user_id.forcemanager_id,
                'value': so.user_id.name
            }
        else:
            fm_salesrep = {
                'id': 95,
                'value': 'Joan Bonell'
            }

        lines_payload = []
        for line in so.order_line:
            fm_prod_id = ""
            if line.product_id and line.product_id.forcemanager_id:
                fm_prod_id = line.product_id.forcemanager_id

            lines_payload.append({
                'productId': fm_prod_id,
                'productName': line.name or "",
                'quantity': line.product_uom_qty,
                'unitPrice': line.price_unit,
            })

        date_created = ""
        if so.date_order:
            date_created = fields.Datetime.to_string(so.date_order).replace(" ", "T") + "Z"

        fm_status = so.forcemanager_status or ""
        
        # x_entrega_mismo_comercial => 'Z_Entrega_mismo_comercial'
        entrega_str = ""
        if so.x_entrega_mismo_comercial == 'si':
            entrega_str = "Si"
        elif so.x_entrega_mismo_comercial == 'no':
            entrega_str = "No"

        # Marcar 'deleted' si en Odoo está cancelado
        is_deleted = (so.state == 'cancel')

        data.update({
            'accountId': fm_account_id,
            'currencyId': currency_val,
            'salesRepId': fm_salesrep,
            'dateCreated': date_created or None,
            'lines': lines_payload,

            'status': fm_status,
            'Z_Entrega_mismo_comercial': entrega_str,
            'deleted': is_deleted,
        })
        return data

    
    # -------------------------------------------------------------------------
    # AUXILIARES DE DOMAIN
    # -------------------------------------------------------------------------
    def _build_domain_for_odoo2fm(self, last_sync_date):
        """
        Construye un dominio:
         - (A) write_date > last_sync_date
         - (B) forcemanager_id = False
         - (C) synced_with_forcemanager = False
        => Triple OR si existe last_sync_date, de lo contrario doble OR para (B,C).
        """
        if last_sync_date:
            return [
                '|', '|',
                ('write_date', '>', last_sync_date),
                ('forcemanager_id', '=', False),
                ('synced_with_forcemanager', '=', False),
            ]
        else:
            return [
                '|',
                ('forcemanager_id', '=', False),
                ('synced_with_forcemanager', '=', False),
            ]
            
    # -------------------------------------------------------------------------
    # Last sync date
    # -------------------------------------------------------------------------
    def _get_last_sync_date(self, entity):
        return self.env['forcemanager.api'].get_last_sync_date(entity)

    def _update_last_sync_date(self, entity):
        self.env['forcemanager.api'].set_last_sync_date(entity)
        _logger.info("[_update_last_sync_date] Fecha de sync actualizada para '%s'.", entity)
    

   # -------------------------------------------------------------------------
    # ACCOUNTS (res.partner con is_company=True)
    # -------------------------------------------------------------------------
    def sync_accounts(self):
        _logger.info("[sync_accounts] Iniciando envío de 'accounts' a FM.")

        last_sync_date = self._get_last_sync_date('accounts')
        domain = self._build_domain_for_odoo2fm(last_sync_date)
        # Filtramos solo las empresas
        domain.insert(0, ('is_company', '=', True))

        partners = self.env['res.partner'].search(domain)
        if not partners:
            _logger.info("[sync_accounts] No hay partners que enviar (dominio=%s).", domain)
            return

        _logger.info("[sync_accounts] Encontrados %d 'accounts' para enviar (dominio=%s).", len(partners), domain)

        to_create = partners.filtered(lambda p: not p.forcemanager_id)
        to_update = partners - to_create

        # =========== CREAR (POST) => Fallback 1x1 para obtener la ID real ===========
        if to_create:
            for partner in to_create:
                single_data = self._prepare_single_account_payload(partner, is_update=False)
                resp = self.env['forcemanager.api']._perform_request("accounts", method='POST', payload=single_data)
                if resp and resp.get('id'):
                    partner.forcemanager_id = str(resp['id'])
                partner.synced_with_forcemanager = True

        # =========== ACTUALIZAR (PUT) en bulk, mantenemos el approach existente =====
        if to_update:
            endpoint_bulk_update = "accounts/bulk"
            if to_update and self._has_bulk_endpoint(endpoint_bulk_update):
                bulk_payload_update = []
                for p in to_update:
                    single_data = self._prepare_single_account_payload(p, is_update=True)
                    bulk_payload_update.append({
                        "guid": f"odoo_update_{p.id}",
                        "data": single_data
                    })
                resp = self.env['forcemanager.api']._perform_request(endpoint_bulk_update, method='PUT', payload=bulk_payload_update)
                self._process_bulk_update_response(resp, to_update)
            else:
                # Fallback 1x1
                for p in to_update:
                    single_data = self._prepare_single_account_payload(p, is_update=True)
                    endpoint = f"accounts/{p.forcemanager_id}"
                    self.env['forcemanager.api']._perform_request(endpoint, method='PUT', payload=single_data)
                    p.synced_with_forcemanager = True

        self._update_last_sync_date('accounts')
        _logger.info("[sync_accounts] Finalizada la sincronización de cuentas.")




    # -------------------------------------------------------------------------
    # CONTACTS (res.partner con is_company=False)
    # -------------------------------------------------------------------------
    def sync_contacts(self):
        _logger.info("[sync_contacts] Iniciando envío de 'contacts' a FM.")

        last_sync_date = self._get_last_sync_date('contacts')
        domain = self._build_domain_for_odoo2fm(last_sync_date)
        domain.insert(0, ('is_company', '=', False))

        contacts = self.env['res.partner'].search(domain)
        if not contacts:
            _logger.info("[sync_contacts] No hay contactos que enviar (dominio=%s).", domain)
            return

        _logger.info("[sync_contacts] Encontrados %d 'contacts' para enviar (dominio=%s).", len(contacts), domain)

        to_create = contacts.filtered(lambda c: not c.forcemanager_id)
        to_update = contacts - to_create

        # =========== CREAR (POST) => 1x1 para obtener ID ===========
        if to_create:
            for c in to_create:
                single_pl = self._prepare_single_contact_payload(c)
                response = self.env['forcemanager.api']._perform_request("contacts", method='POST', payload=single_pl)
                if response and isinstance(response, dict) and response.get('id'):
                    c.forcemanager_id = response['id']
                c.with_context(sync_from_forcemanager=True).write({'synced_with_forcemanager': True})

        # =========== ACTUALIZAR =============
        if to_update:
            payload_update = []
            for c in to_update:
                payload_update.append({
                    "guid": f"odoo_update_{c.id}",
                    "data": self._prepare_single_contact_payload_for_update(c),
                })

            endpoint_update = "contacts/bulk"
            if payload_update and self._has_bulk_endpoint(endpoint_update):
                _logger.info("[sync_contacts][BULK UPDATE] %d → %s", len(payload_update), endpoint_update)
                resp = self.env['forcemanager.api']._perform_request(endpoint_update, method='PUT', payload=payload_update)
                self._process_bulk_update_response(resp, to_update)
            else:
                _logger.warning("[sync_contacts] /contacts/bulk (PUT) no disponible. Fallback 1x1.")
                for c in to_update:
                    single_pl = self._prepare_single_contact_payload_for_update(c)
                    ep = f"contacts/{c.forcemanager_id}"
                    self.env['forcemanager.api']._perform_request(ep, method='PUT', payload=single_pl)
                    c.with_context(sync_from_forcemanager=True).write({'synced_with_forcemanager': True})

        self._update_last_sync_date('contacts')
        _logger.info("[sync_contacts] Finalizada la sincronización de contactos.")

        
    # -------------------------------------------------------------------------
    # PRODUCTS (product.template)
    # -------------------------------------------------------------------------
    def sync_products(self):
        """
        Envía (ODoo→FM) y, además, primero verifica que los productos en FM sigan siendo válidos:
        - Si no existen en Odoo o su categoría no es b2b_available, se eliminan en FM.
        """
        _logger.info("[sync_products] Iniciando envío de productos a ForceManager.")

        # 1) Verificar los productos ya existentes en FM (y borrar los que no apliquen)
        self.verificar_productos_forcemanager_sincronizados()

        # 2) Filtrar productos Odoo que SÍ se deben subir/actualizar a FM
        last_sync = self._get_last_sync_date('products')
        domain = self._build_domain_for_odoo2fm(last_sync)
        # Añadir condición: categoría con b2b_available = True
        domain.insert(0, ('categ_id.b2b_available', '=', True))

        products = self.env['product.template'].search(domain)
        if not products:
            _logger.info("[sync_products] No hay productos que enviar (dominio=%s).", domain)
            return

        _logger.info("[sync_products] Encontrados %d productos. (dominio=%s)", len(products), domain)

        # Separamos en productos a CREAR (sin forcemanager_id) y a ACTUALIZAR (con forcemanager_id)
        to_create = products.filtered(lambda p: not p.forcemanager_id)
        to_update = products - to_create

        # ============== CREAR productos en ForceManager ==============
        if to_create:
            for prod in to_create:
                data = self._prepare_single_product_payload_bulk(prod, is_create=True)
                resp = self.env['forcemanager.api']._perform_request("products", method='POST', payload=data)
                if resp and resp.get('id'):
                    prod.forcemanager_id = str(resp['id'])
                prod.synced_with_forcemanager = True

        # ============== ACTUALIZAR productos en ForceManager ==============
        if to_update:
            for prod in to_update:
                data = self._prepare_single_product_payload_bulk(prod, is_create=False)
                endpoint = f"products/{prod.forcemanager_id}"
                self.env['forcemanager.api']._perform_request(endpoint, method='PUT', payload=data)
                prod.synced_with_forcemanager = True

        # Actualizamos la fecha de la última sincronización
        self._update_last_sync_date('products')
        _logger.info("[sync_products] Sincronización de productos finalizada.")

    def verificar_productos_forcemanager_sincronizados(self):
        """
        1) Descarga la lista actual de productos en ForceManager (GET /products).
        2) Para cada uno de ellos:
        - Si "deleted"=True en FM, quitamos el forcemanager_id en Odoo (para que deje de estar vinculado).
        - Si no está "deleted":
            - Buscamos el producto correspondiente en Odoo (por forcemanager_id).
            - Si NO existe en Odoo, o su categoría NO tiene b2b_available=True,
            se borra el producto en ForceManager (DELETE /products/<id>).
        """
        _logger.info("[verificar_productos_forcemanager_sincronizados] Iniciando verificación en ForceManager...")

        # Ejemplo de cláusula where (depende de la API de FM si la admite o no):
        where_clause = f"(deleted = 'false' OR deleted = 'False')"
        endpoint_url = f"products?where={where_clause}"
        
        fm_products = self.env['forcemanager.api']._perform_request(endpoint_url, method='GET')
        if not fm_products:
            fm_products = []
        elif not isinstance(fm_products, list):
            fm_products = fm_products.get('results', [])

        _logger.info("Se han encontrado %d productos en ForceManager (incluyendo los borrados).", len(fm_products))

        for fm_prod in fm_products:
            fm_id = fm_prod.get('id')
            if not fm_id:
                continue

            # 1) Si ForceManager ya marca "deleted": True => eliminamos el forcemanager_id en Odoo
            if fm_prod.get('deleted') is True:
                _logger.info("Producto FM ID=%s aparece 'deleted' en ForceManager => eliminando vínculo en Odoo.", fm_id)
                product_odoo = self.env['product.template'].search([('forcemanager_id', '=', str(fm_id))], limit=1)
                if product_odoo:
                    product_odoo.write({
                        'forcemanager_id': False,
                        'synced_with_forcemanager': False
                    })
                    _logger.info("Vínculo eliminado en Odoo (product.template ID=%d).", product_odoo.id)
                continue

            # 2) Si NO está "deleted": verificamos su existencia en Odoo
            product_odoo = self.env['product.template'].search([('forcemanager_id', '=', str(fm_id))], limit=1)
            if not product_odoo:
                # No existe en Odoo => BORRAR en FM
                self._eliminar_producto_forcemanager(fm_id, reason="No existe en Odoo")
                continue

            # 3) Existe en Odoo => verificar categoría
            categ = product_odoo.categ_id
            if not categ.b2b_available:
                # La categoría NO está marcada como B2B => BORRAR en FM
                self._eliminar_producto_forcemanager(
                    fm_id,
                    reason=f"Categ '{categ.name}' no es b2b_available"
                )
                continue

            # (Opcional) Más comprobaciones, p.ej. si categ.forcemanager_id se perdió...

        _logger.info("[verificar_productos_forcemanager_sincronizados] Finalizada la verificación.")



    def _eliminar_producto_forcemanager(self, fm_id, reason=""):
        """
        Llama DELETE /products/<fm_id> y hace log del suceso.
        Tras eliminarlo en ForceManager, si existe en Odoo,
        le quitamos el 'forcemanager_id' y marcamos synced_with_forcemanager=False.
        """
        _logger.info("Eliminando producto FM ID=%s en ForceManager (motivo: %s)", fm_id, reason or "N/A")
        endpoint_delete = f"products/{fm_id}"
        try:
            self.env['forcemanager.api']._perform_request(endpoint_delete, method='DELETE')
            _logger.info("Producto FM ID=%s eliminado correctamente en ForceManager.", fm_id)

            # A continuación, quitamos el forcemanager_id en Odoo, si existe
            product_odoo = self.env['product.template'].search([('forcemanager_id', '=', str(fm_id))], limit=1)
            if product_odoo:
                product_odoo.write({
                    'forcemanager_id': False,
                    'synced_with_forcemanager': False
                })
                _logger.info(
                    "Producto Odoo ID=%d: forcemanager_id eliminado y synced_with_forcemanager=False",
                    product_odoo.id
                )

        except Exception as e:
            _logger.warning("Error al eliminar el producto FM ID=%s: %s", fm_id, e)




    # -------------------------------------------------------------------------
    # OPPORTUNITIES (crm.lead)
    # -------------------------------------------------------------------------
    def sync_opportunities(self):
        _logger.info("[sync_opportunities] Iniciando envío de 'opportunities' a FM.")
        last_sync_date = self._get_last_sync_date('opportunities')
        domain = self._build_domain_for_odoo2fm(last_sync_date)

        leads = self.env['crm.lead'].search(domain)
        if not leads:
            _logger.info("[sync_opportunities] No hay leads que enviar (dominio=%s).", domain)
            return

        _logger.info("[sync_opportunities] Encontradas %d leads. (dominio=%s)", len(leads), domain)

        to_create = leads.filtered(lambda l: not l.forcemanager_id)
        to_update = leads - to_create

        # =========== CREAR (POST) => 1x1 para obtener ID ===========
        if to_create:
            for lead in to_create:
                single_pl = self._prepare_single_opportunity_payload(lead, is_create=True)
                resp = self.env['forcemanager.api']._perform_request("opportunities", method='POST', payload=single_pl)
                if resp and isinstance(resp, dict) and resp.get('id'):
                    lead.forcemanager_id = resp['id']
                lead.synced_with_forcemanager = True

        # =========== ACTUALIZAR (PUT) (en bulk o fallback) ======
        if to_update:
            payload_update = []
            for lead in to_update:
                payload_update.append({
                    "guid": f"odoo_update_{lead.id}",
                    "data": self._prepare_single_opportunity_payload(lead, is_create=False),
                })

            endpoint_update = "opportunities/bulk"
            if payload_update and self._has_bulk_endpoint(endpoint_update):
                resp = self.env['forcemanager.api']._perform_request(endpoint_update, method='PUT', payload=payload_update)
                self._process_bulk_update_response(resp, to_update)
            else:
                _logger.warning("[sync_opportunities] /opportunities/bulk (PUT) no disponible. Fallback 1x1.")
                for lead in to_update:
                    single_pl = self._prepare_single_opportunity_payload(lead, is_create=False)
                    ep = f"opportunities/{lead.forcemanager_id}"
                    self.env['forcemanager.api']._perform_request(ep, method='PUT', payload=single_pl)
                    lead.synced_with_forcemanager = True

        self._update_last_sync_date('opportunities')
        _logger.info("[sync_opportunities] Finalizada la sincronización de oportunidades.")


    



    
    # -------------------------------------------------------------------------
    # PREPARAR PAYLOADS
    # -------------------------------------------------------------------------
    def _prepare_single_account_payload(self, partner, is_update=False):
        """
        Construye el dict JSON para 'accounts' al enviar desde Odoo a ForceManager.
        Incluye:
        - 'id' = partner.forcemanager_id (solo si is_update=True y lo tiene)
        - 'name' = partner.name
        - 'Z_nif' = partner.vat
        - 'Z_Nombre_Comercial' = partner.comercial (si existe)
        - 'Z_Recargo_de_equivalencia' = True/False si detecta la fiscal position
        - 'salesRepId1': { 'id': ..., 'value': ... } con el FM ID del usuario (o fallback)
        - 'countryId': { 'id': country.forcemanager_id, 'value': country.name } (si existe)
        """
        payload = {}
        if is_update and partner.forcemanager_id:
            payload['id'] = partner.forcemanager_id

        # 1) Recargo equivalencia
        z_recargo_equivalencia = False
        if (partner.property_account_position_id
            and 'Recargo de Equivalencia' in partner.property_account_position_id.name):
            z_recargo_equivalencia = True

        # 2) Determinar salesRepId1 (con fallback = {id=95, value='Joan Bonell'})
        if partner.user_id and partner.user_id.forcemanager_id:
            salesrep_dict = {
                'id': partner.user_id.forcemanager_id,
                'value': partner.user_id.name,
            }
        else:
            salesrep_dict = {
                'id': 95,
                'value': 'Joan Bonell'
            }

        # 3) countryId
        country_dict = None
        if partner.country_id and partner.country_id.forcemanager_id:
            country_dict = {
                'id': partner.country_id.forcemanager_id,
                'value': partner.country_id.name,
            }

        # 4) Construcción del payload
        payload.update({
            'name': partner.name or "(Sin nombre)",
            'address1': partner.street or "",
            'address2': partner.street2 or "",
            'city': partner.city or "",
            'postcode': partner.zip or "",
            'region': partner.state_id.name if partner.state_id else "",
            'countryId': country_dict,   # En lugar de "country"
            'phone': partner.phone or "",
            'phone2': partner.mobile or "",
            'email': partner.email or "",
            'website': partner.website or "",
            'comment': partner.comment or "",
            'Z_nif': partner.vat or "",
            'Z_Nombre_Comercial': getattr(partner, 'comercial', "") or "",
            'Z_Recargo_de_equivalencia': z_recargo_equivalencia,
            'salesRepId1': salesrep_dict,
        })
        return payload



    def _prepare_single_contact_payload(self, contact):
        """
        Payload para CREAR/ACTUALIZAR un contacto en FM.
        - salesRepId => con fallback a {id=95, value='Joan Bonell'}
        - countryId => { 'id': X, 'value': Y } si existe
        """
        # 1) Determinar salesRepId (con fallback)
        if contact.user_id and contact.user_id.forcemanager_id:
            fm_salesrep = {
                'id': contact.user_id.forcemanager_id,
                'value': contact.user_id.name
            }
        else:
            fm_salesrep = {
                'id': 95,
                'value': 'Joan Bonell'
            }

        # 2) Determinar accountId
        account_id_dict = None
        if contact.parent_id and contact.parent_id.forcemanager_id:
            account_id_dict = {
                'id': contact.parent_id.forcemanager_id,
                'value': contact.parent_id.name
            }

        # 3) countryId
        country_val = None
        if contact.country_id and contact.country_id.forcemanager_id:
            country_val = {
                'id': contact.country_id.forcemanager_id,
                'value': contact.country_id.name,
            }

        # 4) Construcción final
        return {
            'firstName': contact.name or "",
            'lastName': "",  # si quieres separar name en first/last, hacerlo aquí
            'phone1': contact.phone or "",
            'phone2': contact.mobile or "",
            'email': contact.email or "",
            'comment': contact.comment or "",
            'typeId': {'id': 0, 'value': contact.function or ""},
            'accountId': account_id_dict,
            'salesRepId': fm_salesrep,
            'UseCompanyAddress': False,
            'address1': contact.street or "",
            'address2': contact.street2 or "",
            'city': contact.city or "",
            'postcode': contact.zip or "",
            'region': contact.state_id.name if contact.state_id else "",
            'countryId': country_val,
        }


    def _prepare_single_product_payload_bulk(self, product, is_create=True):
        """
        Construye el 'data' para la exportación en /products/bulk (POST/PUT).
        Enviamos:
        - model => product.name
        - description => product.description_sale
        - price => product.list_price
        - cost => product.standard_price
        - categoryId => int(product.categ_id.forcemanager_id) si existe
        - stock => product.qty_available
        """
        cat_id = False
        if product.categ_id and product.categ_id.forcemanager_id:
            try:
                cat_id = int(product.categ_id.forcemanager_id)
            except ValueError:
                cat_id = False

        data_obj = {}
        if not is_create and product.forcemanager_id:
            # ForceManager exige mandar "id" como int
            try:
                data_obj['id'] = int(product.forcemanager_id)
            except ValueError:
                data_obj['id'] = 0  # en caso extremo

        data_obj.update({
            "extId": str(product.id),
            "model": product.name or "(Sin nombre)",
            # Usamos description_sale para que coincida con lo que recibimos del otro lado
            "description": product.description_sale or "",
            "price": product.list_price or 0.0,
            "cost": product.standard_price or 0.0,
            "maxDiscount": 0,
            "permissionLevel": 2,
            # Enviamos el stock disponible
            "stock": product.qty_available or 0.0,
            "notAvailable": False,
            "readOnly": False,
        })
        if cat_id:
            data_obj["categoryId"] = cat_id

        return data_obj


    # -------------------------------------------------------------------------
    # ENDPOINT DETECTION & RESPONSES
    # -------------------------------------------------------------------------
    def _has_bulk_endpoint(self, endpoint):
        """
        Comprueba si FM soporta GET <endpoint>?limit=0 sin 404 => True.
        Se usa igual en POST y PUT. 
        """
        test_url = endpoint + "?limit=0"
        _logger.info("[_has_bulk_endpoint] Probando GET: %s", test_url)
        try:
            self.env['forcemanager.api']._perform_request(test_url, method='GET')
            return True
        except Exception as e:
            _logger.warning("[_has_bulk_endpoint] => No soportado: %s", e)
            return False

    def _process_bulk_create_response(self, response_list, recordset):
        """
        Lee la respuesta, e.g. [{"id": X, "guid": "odoo_create_XX"}, ...]
        """
        if not response_list or not isinstance(response_list, list):
            _logger.warning("[_process_bulk_create_response] Respuesta no es lista => no se mapea.")
            return

        guid_map = {f"odoo_create_{rec.id}": rec for rec in recordset}
        for item in response_list:
            guid = item.get('guid')
            fm_id = item.get('id')
            if guid and fm_id:
                rec = guid_map.get(guid)
                if rec:
                    rec.forcemanager_id = str(fm_id)
                    rec.synced_with_forcemanager = True

    def _process_bulk_update_response(self, response_list, recordset):
        """
        Lee la respuesta, e.g. [{"id": X, "odoo_local_id": Y}, ...] (varía).
        Normalmente => se marca synced = True.
        """
        if not response_list or not isinstance(response_list, list):
            _logger.warning("[_process_bulk_update_response] Respuesta no es lista => no se mapea.")
            return

        # Normalmente en PUT ya había forcemanager_id => lo marcamos True
        # Detectamos 'odoo_local_id' si lo hay:
        local_ids = {}
        for item in response_list:
            local_id = item.get('odoo_local_id')
            if local_id:
                local_ids[local_id] = item.get('id')

        if local_ids:
            # Si la API devuelven local_id => actualizamos 1 a 1
            for rec in recordset:
                if rec.id in local_ids:
                    rec.synced_with_forcemanager = True
        else:
            # Marcamos todos directamente
            recordset.write({'synced_with_forcemanager': True})

    def _assign_fm_id_single_create(self, response_list, record):
        """
        Fallback 1x1 => Se espera una list con un único dict => {"id":..., ...}.
        """
        if not response_list or not isinstance(response_list, list):
            return
        if response_list:
            item = response_list[0]
            fm_id = item.get('id')
            if fm_id:
                record.forcemanager_id = str(fm_id)
                record.synced_with_forcemanager = True

    

    def _prepare_single_opportunity_payload(self, lead, is_create=True):
        """
        Construye el payload para las oportunidades (crm.lead).
        - salesRepId => con fallback a {id=95, value='Joan Bonell'}
        """
        # 1) Determinar accountId1
        fm_account_id = None
        if lead.partner_id and lead.partner_id.forcemanager_id:
            fm_account_id = {
                'id': lead.partner_id.forcemanager_id,
                'value': lead.partner_id.name
            }

        # 2) Determinar statusId (etapa)
        fm_stage = {'value': lead.stage_id.name} if lead.stage_id else None

        # 3) Comercial => salesRepId con fallback
        if lead.user_id and lead.user_id.forcemanager_id:
            fm_salesrep = {
                'id': lead.user_id.forcemanager_id,
                'value': lead.user_id.name
            }
        else:
            fm_salesrep = {
                'id': 95,
                'value': 'Joan Bonell'
            }

        # 4) Probabilidad => se suele mandar como 0..1, por lo que lead.probability/100
        fm_prob = (lead.probability or 0.0) / 100.0

        # 5) Construcción del payload
        payload = {}
        if not is_create and lead.forcemanager_id:
            payload['id'] = lead.forcemanager_id

        payload.update({
            'reference': lead.name or "(Sin nombre)",
            'accountId1': fm_account_id,
            'statusId': fm_stage,
            'salesRepId': fm_salesrep,
            'comments': lead.description or "",
            'total': lead.expected_revenue or 0.0,
            'salesProbability': fm_prob,
        })

        # 6) Fecha forecast
        if lead.date_deadline:
            payload['salesForecastDate'] = f"{lead.date_deadline}T00:00:00Z"

        return payload

