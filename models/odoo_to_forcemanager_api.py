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
        self.sync_accounts()
        self.sync_contacts()
        self.sync_products()
        self.sync_opportunities()
        self.sync_orders()

        _logger.info("<<< [OdooToForceManagerAPI] action_sync_to_forcemanager() END")

   # -------------------------------------------------------------------------
    # ACCOUNTS (res.partner con is_company=True)
    # -------------------------------------------------------------------------
    def sync_accounts(self):
        """
        Envía las empresas a ForceManager:
         - Si forcemanager_id está vacío => POST.
         - Si forcemanager_id existe => PUT.
         - Dominio: triple OR (write_date > last_sync, forcemanager_id=False, synced_with_forcemanager=False).
        """
        _logger.info("[sync_accounts] Iniciando envío de 'accounts' a FM.")

        last_sync_date = self._get_last_sync_date('accounts')
        domain = self._build_domain_for_odoo2fm(last_sync_date)
        # Añadimos la condición de is_company=True
        domain.insert(0, ('is_company', '=', True))

        partners = self.env['res.partner'].search(domain)
        if not partners:
            _logger.info("[sync_accounts] No hay partners que enviar (dominio=%s).", domain)
            return

        _logger.info("[sync_accounts] Encontrados %d 'accounts' para enviar (dominio=%s).", len(partners), domain)

        # Separar crear / actualizar
        to_create = partners.filtered(lambda p: not p.forcemanager_id)
        to_update = partners - to_create

        # =========== CREAR (POST) ===========
        if to_create:
            bulk_payload_create = []
            for p in to_create:
                single_data = self._prepare_single_account_payload(p, is_update=False)
                guid_val = f"odoo_create_{p.id}"
                bulk_payload_create.append({"guid": guid_val, "data": single_data})

            endpoint_bulk_create = "accounts/bulk"
            if bulk_payload_create and self._has_bulk_endpoint(endpoint_bulk_create):
                _logger.info("[sync_accounts][BULK CREATE] %d records → %s", len(bulk_payload_create), endpoint_bulk_create)
                resp = self.env['forcemanager.api']._perform_request(endpoint_bulk_create, method='POST', payload=bulk_payload_create)
                self._process_bulk_create_response(resp, to_create)
            else:
                _logger.warning("[sync_accounts] /accounts/bulk (POST) no disponible. Fallback 1x1.")
                for p in to_create:
                    single_data = self._prepare_single_account_payload(p, is_update=False)
                    endpoint = "accounts"
                    response = self.env['forcemanager.api']._perform_request(endpoint, method='POST', payload=single_data)
                    if response and isinstance(response, dict) and response.get('id'):
                        p.forcemanager_id = response['id']
                    p.synced_with_forcemanager = True

        # =========== ACTUALIZAR (PUT) ===========
        if to_update:
            bulk_payload_update = []
            for p in to_update:
                single_data = self._prepare_single_account_payload(p, is_update=True)
                guid_val = f"odoo_update_{p.id}"
                bulk_payload_update.append({"guid": guid_val, "data": single_data})

            endpoint_bulk_update = "accounts/bulk"
            if bulk_payload_update and self._has_bulk_endpoint(endpoint_bulk_update):
                _logger.info("[sync_accounts][BULK UPDATE] %d records → %s", len(bulk_payload_update), endpoint_bulk_update)
                resp = self.env['forcemanager.api']._perform_request(endpoint_bulk_update, method='PUT', payload=bulk_payload_update)
                self._process_bulk_update_response(resp, to_update)
            else:
                _logger.warning("[sync_accounts] /accounts/bulk (PUT) no disponible. Fallback 1x1.")
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

        # =========== CREAR ===========
        if to_create:
            payload_create = []
            for c in to_create:
                payload_create.append({
                    "guid": f"odoo_create_{c.id}",
                    "data": self._prepare_single_contact_payload(c),
                })

            endpoint_create = "contacts/bulk"
            if payload_create and self._has_bulk_endpoint(endpoint_create):
                _logger.info("[sync_contacts][BULK CREATE] %d → %s", len(payload_create), endpoint_create)
                resp = self.env['forcemanager.api']._perform_request(endpoint_create, method='POST', payload=payload_create)
                self._process_bulk_create_response(resp, to_create)
            else:
                _logger.warning("[sync_contacts] /contacts/bulk (POST) no disponible. Fallback 1x1.")
                for c in to_create:
                    single_pl = self._prepare_single_contact_payload(c)
                    response = self.env['forcemanager.api']._perform_request("contacts", method='POST', payload=single_pl)
                    if response and isinstance(response, dict) and response.get('id'):
                        c.forcemanager_id = response['id']
                    c.synced_with_forcemanager = True

        # =========== ACTUALIZAR ===========
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
                    c.synced_with_forcemanager = True

        self._update_last_sync_date('contacts')
        _logger.info("[sync_contacts] Finalizada la sincronización de contactos.")
        
    # -------------------------------------------------------------------------
    # PRODUCTS (product.template)
    # -------------------------------------------------------------------------
    def sync_products(self):
        """
        Envía los productos a ForceManager usando /products/bulk (si existe),
        o fallback 1x1. Incluye la triple OR:
        - (A) write_date > last_sync
        - (B) forcemanager_id=False
        - (C) synced_with_forcemanager=False
        para detectar los productos que deben subirse/actualizarse.

        Se actualiza y envía el stock (product.qty_available) a ForceManager,
        y se envía 'description_sale' como 'description', que es lo que
        ForceManager espera y lo que luego recibimos en forcemanager_to_odoo_api.
        """
        _logger.info("[sync_products] Iniciando envío de productos a ForceManager.")
        last_sync = self._get_last_sync_date('products')
        domain = self._build_domain_for_odoo2fm(last_sync)

        products = self.env['product.template'].search(domain)
        if not products:
            _logger.info("[sync_products] No hay productos que enviar (dominio=%s).", domain)
            return

        _logger.info("[sync_products] Encontrados %d productos. (dominio=%s)", len(products), domain)

        to_create = products.filtered(lambda p: not p.forcemanager_id)
        to_update = products - to_create

        # =========== CREAR ===========
        if to_create:
            bulk_payload_create = []
            for prod in to_create:
                guid_str = f"odoo_create_{prod.id}"
                data_obj = self._prepare_single_product_payload_bulk(prod, is_create=True)
                bulk_payload_create.append({"guid": guid_str, "data": data_obj})

            endpoint_create = "products/bulk"
            if bulk_payload_create and self._has_bulk_endpoint(endpoint_create):
                _logger.info("[sync_products][BULK CREATE] Enviando %d → %s", len(bulk_payload_create), endpoint_create)
                response = self.env['forcemanager.api']._perform_request(endpoint_create, method="POST", payload=bulk_payload_create)
                self._process_bulk_create_response(response, to_create)
            else:
                _logger.warning("[sync_products] /products/bulk (POST) no disponible. Fallback 1x1.")
                for prod in to_create:
                    single_item = {
                        "guid": f"odoo_create_{prod.id}",
                        "data": self._prepare_single_product_payload_bulk(prod, is_create=True)
                    }
                    resp = self.env['forcemanager.api']._perform_request("products/bulk", method="POST", payload=[single_item])
                    self._assign_fm_id_single_create(resp, prod)

        # =========== ACTUALIZAR ===========
        if to_update:
            bulk_payload_update = []
            for prod in to_update:
                guid_str = f"odoo_update_{prod.id}"
                data_obj = self._prepare_single_product_payload_bulk(prod, is_create=False)
                bulk_payload_update.append({"guid": guid_str, "data": data_obj})

            endpoint_update = "products/bulk"
            if bulk_payload_update and self._has_bulk_endpoint(endpoint_update):
                _logger.info("[sync_products][BULK UPDATE] Enviando %d → %s", len(bulk_payload_update), endpoint_update)
                response = self.env['forcemanager.api']._perform_request(endpoint_update, method="PUT", payload=bulk_payload_update)
                self._process_bulk_update_response(response, to_update)
            else:
                _logger.warning("[sync_products] /products/bulk (PUT) no disponible. Fallback 1x1.")
                for prod in to_update:
                    single_item = {
                        "guid": f"odoo_update_{prod.id}",
                        "data": self._prepare_single_product_payload_bulk(prod, is_create=False),
                    }
                    resp = self.env['forcemanager.api']._perform_request("products/bulk", method="PUT", payload=[single_item])
                    prod.synced_with_forcemanager = True

        self._update_last_sync_date('products')
        _logger.info("[sync_products] Sincronización de productos finalizada.")



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

        # =========== CREAR ===========
        if to_create:
            payload_create = []
            for lead in to_create:
                payload_create.append({
                    "guid": f"odoo_create_{lead.id}",
                    "data": self._prepare_single_opportunity_payload(lead, is_create=True),
                })

            endpoint_create = "opportunities/bulk"
            if payload_create and self._has_bulk_endpoint(endpoint_create):
                resp = self.env['forcemanager.api']._perform_request(endpoint_create, method='POST', payload=payload_create)
                self._process_bulk_create_response(resp, to_create)
            else:
                _logger.warning("[sync_opportunities] /opportunities/bulk (POST) no disponible. Fallback 1x1.")
                for lead in to_create:
                    single_pl = self._prepare_single_opportunity_payload(lead, is_create=True)
                    resp = self.env['forcemanager.api']._perform_request("opportunities", method='POST', payload=single_pl)
                    if resp and isinstance(resp, dict) and resp.get('id'):
                        lead.forcemanager_id = resp['id']
                    lead.synced_with_forcemanager = True

        # =========== ACTUALIZAR ===========
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
    # ORDERS (sale.order)
    # -------------------------------------------------------------------------
    def sync_orders(self):
        """
        Envía pedidos (sale.order) de Odoo a ForceManager:
        - Filtra por triple OR (write_date > last_sync, forcemanager_id=False, synced_with_forcemanager=False)
        - Separa en pedidos a CREAR (POST /sales) o ACTUALIZAR (PUT /sales/{id})
        - Usa forcemanager_id en sale.order para enlazar
        - Envía 'x_entrega_mismo_comercial' => 'Z_Entrega_mismo_comercial' ("Si"/"No")
        - Envía 'forcemanager_status' => 'status' si lo deseas
        """
        _logger.info("[sync_orders] Iniciando envío de 'orders' a FM.")
        last_sync_date = self._get_last_sync_date('orders')
        domain = self._build_domain_for_odoo2fm(last_sync_date)

        orders = self.env['sale.order'].search(domain)
        if not orders:
            _logger.info("[sync_orders] No hay pedidos que enviar (dominio=%s).", domain)
            return

        _logger.info("[sync_orders] Encontrados %d pedidos. (dominio=%s)", len(orders), domain)

        to_create = orders.filtered(lambda o: not o.forcemanager_id)
        to_update = orders - to_create

        # =========== CREAR ===========
        if to_create:
            payload_create = []
            for so in to_create:
                payload_create.append({
                    "guid": f"odoo_create_{so.id}",
                    "data": self._prepare_single_order_payload(so, is_create=True),
                })

            endpoint_create = "sales/bulk"
            if payload_create and self._has_bulk_endpoint(endpoint_create):
                resp = self.env['forcemanager.api']._perform_request(endpoint_create, method='POST', payload=payload_create)
                self._process_bulk_create_response(resp, to_create)
            else:
                _logger.warning("[sync_orders] /sales/bulk (POST) no disponible. Fallback 1x1.")
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
        """
        Construye el payload para un 'sale.order' => ForceManager 'sales'.
        - Mapeamos 'forcemanager_status' => 'status'
        - Mapeamos 'x_entrega_mismo_comercial' => 'Z_Entrega_mismo_comercial'
        - Si la orden está en estado cancel => 'deleted': True (opcional)
        """
        data = {}
        if not is_create and so.forcemanager_id:
            data['id'] = so.forcemanager_id

        # 1) Identificar la cuenta
        fm_account_id = None
        if so.partner_id and so.partner_id.forcemanager_id:
            fm_account_id = {'id': so.partner_id.forcemanager_id, 'value': so.partner_id.name}

        # 2) Moneda
        currency_val = {'value': so.currency_id.name} if so.currency_id else None

        # 3) Comercial
        fm_salesrep = None
        if so.user_id and so.user_id.forcemanager_id:
            fm_salesrep = {'id': so.user_id.forcemanager_id, 'value': so.user_id.name}

        # 4) Líneas
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

        # 5) dateCreated => so.date_order
        fm_date_str = ""
        if so.date_order:
            fm_date_str = fields.Datetime.to_string(so.date_order).replace(" ", "T") + "Z"

        # 6) forcemanager_status => 'status'
        fm_status = so.forcemanager_status or ""

        # 7) x_entrega_mismo_comercial => "Z_Entrega_mismo_comercial"
        entrega_str = ""
        if so.x_entrega_mismo_comercial == 'si':
            entrega_str = "Si"
        elif so.x_entrega_mismo_comercial == 'no':
            entrega_str = "No"

        # 8) Mark 'deleted' if Odoo is canceled (opcional)
        #    Si deseas que al cancelar en Odoo, se elimine en ForceManager, haz:
        is_deleted = (so.state == 'cancel')

        # 9) Construir data
        data.update({
            'accountId': fm_account_id,
            'currencyId': currency_val,
            'salesRepId': fm_salesrep,
            'dateCreated': fm_date_str or None,
            'lines': lines_payload,

            # Campos custom
            'status': fm_status,                     # Forcemanager status
            'Z_Entrega_mismo_comercial': entrega_str, # "Si"/"No"
            'deleted': is_deleted,                   # Si está cancelado en Odoo => se marca en FM
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
    # PREPARAR PAYLOADS
    # -------------------------------------------------------------------------
    def _prepare_single_account_payload(self, partner, is_update=False):
        """
        Contruye el dict JSON para 'accounts'.
        ...
        (id, name, address, etc.)
        """
        z_recargo_equivalencia = False
        if partner.property_account_position_id and 'Recargo de Equivalencia' in partner.property_account_position_id.name:
            z_recargo_equivalencia = True

        raw_name = partner.name or "(Sin nombre)"
        # Valor ficticio por si no hay FM salesrep:
        fm_salesrep_id = 95
        if partner.user_id and partner.user_id.forcemanager_id:
            fm_salesrep_id = partner.user_id.forcemanager_id

        payload = {}
        if is_update and partner.forcemanager_id:
            payload['id'] = partner.forcemanager_id

        payload.update({
            'name': raw_name,
            'address1': partner.street or "",
            'address2': partner.street2 or "",
            'city': partner.city or "",
            'postcode': partner.zip or "",
            'region': partner.state_id.name if partner.state_id else "",
            'country': partner.country_id.name if partner.country_id else "",
            'phone': partner.phone or "",
            'phone2': partner.mobile or "",
            'email': partner.email or "",
            'website': partner.website or "",
            'comment': partner.comment or "",
            'Z_nif': partner.vat or "",
            'Z_Nombre_Comercial': getattr(partner, 'comercial', "") or "",
            'Z_Recargo_de_equivalencia': z_recargo_equivalencia,
            'salesRepId1': fm_salesrep_id,
        })
        return payload

    def _prepare_single_contact_payload(self, contact):
        """
        Payload para CREAR un contacto en FM.
        """
        fm_salesrep = None
        if contact.user_id and contact.user_id.forcemanager_id:
            fm_salesrep = {'id': contact.user_id.forcemanager_id, 'value': contact.user_id.name}

        account_id_dict = None
        if contact.parent_id and contact.parent_id.forcemanager_id:
            account_id_dict = {'id': contact.parent_id.forcemanager_id, 'value': contact.parent_id.name}

        first_name = contact.name or ""
        # Si deseas separar name en firstName/lastName, hazlo, de lo contrario dejas last_name en blanco.

        country_val = {'value': contact.country_id.name} if contact.country_id else None

        return {
            'firstName': first_name,
            'lastName': "",
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

    def _prepare_single_contact_payload_for_update(self, contact):
        """
        Similar a _prepare_single_contact_payload, pero con 'id': forcemanager_id.
        """
        data = self._prepare_single_contact_payload(contact)
        if contact.forcemanager_id:
            data['id'] = contact.forcemanager_id
        data['odoo_local_id'] = contact.id  # no siempre es necesario, pero para mapping
        return data

    def _prepare_single_opportunity_payload(self, lead, is_create=True):
        """
        Payload para las oportunidades (crm.lead).
        """
        fm_account_id = None
        if lead.partner_id and lead.partner_id.forcemanager_id:
            fm_account_id = {'id': lead.partner_id.forcemanager_id, 'value': lead.partner_id.name}
        fm_stage = {'value': lead.stage_id.name} if lead.stage_id else None
        fm_salesrep = None
        if lead.user_id and lead.user_id.forcemanager_id:
            fm_salesrep = {'id': lead.user_id.forcemanager_id, 'value': lead.user_id.name}
        fm_prob = (lead.probability or 0.0) / 100.0

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
        if lead.date_deadline:
            payload['salesForecastDate'] = f"{lead.date_deadline}T00:00:00Z"
        return payload

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

    # -------------------------------------------------------------------------
    # Last sync date
    # -------------------------------------------------------------------------
    def _get_last_sync_date(self, entity):
        return self.env['forcemanager.api'].get_last_sync_date(entity)

    def _update_last_sync_date(self, entity):
        self.env['forcemanager.api'].set_last_sync_date(entity)
        _logger.info("[_update_last_sync_date] Fecha de sync actualizada para '%s'.", entity)

