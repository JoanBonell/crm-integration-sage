# models/forcemanager_to_odoo_api.py

import logging
from odoo import api, fields, models
from datetime import datetime

_logger = logging.getLogger(__name__)

class ForceManagerToOdooAPI(models.TransientModel):
    _name = 'forcemanager.to.odoo'
    _description = 'Sync from ForceManager to Odoo (accounts, contacts, products, opportunities)'

    @api.model
    def action_sync_from_forcemanager(self):
        """
        Entrada principal para sincronizar ForceManager → Odoo.
        """
        _logger.info(">>> [ForceManagerToOdooAPI] action_sync_from_forcemanager() START")

        self.sync_accounts()
        self.sync_contacts()
        self.sync_opportunities()
        self.sync_products()
        self.sync_orders() 
        
        _logger.info("<<< [ForceManagerToOdooAPI] action_sync_from_forcemanager() END")

    # -------------------------------------------------------------------------
    # ACCOUNTS
    # -------------------------------------------------------------------------
    def sync_accounts(self):
        _logger.info(">>> [sync_accounts] Iniciando sincronización de cuentas (accounts)")

        last_sync = self._get_last_sync_date('accounts')
        if not last_sync:
            date_updated_str = '2025-01-01T00:00:00Z'
        else:
            tmp = fields.Datetime.to_string(last_sync)
            date_updated_str = tmp.replace(' ', 'T') + 'Z'

        where_clause = f"(dateUpdated gt '{date_updated_str}' OR dateCreated gt '{date_updated_str}')"
        endpoint_url = f"accounts?where={where_clause}"
        _logger.info("[sync_accounts] GET /api/v4/%s", endpoint_url)

        response = self.env['forcemanager.api']._perform_request(endpoint_url, method='GET')
        if not response:
            _logger.warning("[sync_accounts] Respuesta vacía o error. Abortando.")
            return

        fm_account_list = response if isinstance(response, list) else response.get('results', [])
        _logger.info("[sync_accounts] Recibidos %d accounts desde ForceManager", len(fm_account_list))

        for fm_acc in fm_account_list:
            fm_id_raw = fm_acc.get('id')
            try:
                fm_id = int(fm_id_raw) if fm_id_raw else 0
            except ValueError:
                fm_id = 0

            partner = self.env['res.partner'].search([
                ('forcemanager_id', '=', fm_id),
                ('is_company', '=', True),
            ], limit=1)

            # Campos directos
            raw_name = fm_acc.get('name') or "(Sin nombre)"
            street = fm_acc.get('address1') or ""
            street2 = fm_acc.get('address2') or ""
            city = fm_acc.get('city') or ""
            zipcode = fm_acc.get('postcode') or ""
            comment_html = fm_acc.get('comment') or ""
            nombre_comercial = fm_acc.get('Z_Nombre_Comercial') or False
            nif = fm_acc.get('Z_nif') or ""
            website = fm_acc.get('website') or ""

            # =====================================================================
            # 1) Determinar país / provincia
            # =====================================================================
            fm_country_dict = fm_acc.get('countryId', {})
            fm_country_id = 0
            fm_country_str = ""
            if isinstance(fm_country_dict, dict):
                raw_cid = fm_country_dict.get('id')
                try:
                    fm_country_id = int(raw_cid) if raw_cid else 0
                except ValueError:
                    fm_country_id = 0
                fm_country_str = fm_country_dict.get('value', "")

            country_rec = False
            if fm_country_id > 0:
                country_rec = self.env['res.country'].search([('forcemanager_id', '=', fm_country_id)], limit=1)
            if not country_rec and fm_country_str:
                country_rec = self.env['res.country'].search([('name', 'ilike', fm_country_str)], limit=1)
            if not country_rec:
                fallback_country = self.env['res.country'].search([('code', '=', 'ES')], limit=1)
                if fallback_country:
                    country_rec = fallback_country

            region_name = fm_acc.get('region') or ""
            state_rec = False
            if region_name and country_rec:
                state_rec = self.env['res.country.state'].search([
                    ('name', 'ilike', region_name),
                    ('country_id', '=', country_rec.id),
                ], limit=1)

            # =====================================================================
            # 2) Determinar usuario comercial (salesRepId1)
            # =====================================================================
            salesrep_data = fm_acc.get('salesRepId1') or {}
            fm_salesrep_id_raw = salesrep_data.get('id')
            try:
                fm_salesrep_id = int(fm_salesrep_id_raw) if fm_salesrep_id_raw else 0
            except ValueError:
                fm_salesrep_id = 0

            rep_name = salesrep_data.get('value') or ""

            user_id = False
            if fm_salesrep_id > 0:
                user_by_fmid = self.env['res.users'].search([('forcemanager_id', '=', fm_salesrep_id)], limit=1)
                if user_by_fmid:
                    user_id = user_by_fmid.id
                else:
                    # Buscar por nombre
                    if rep_name:
                        user_by_name = self.env['res.users'].search([('name', '=', rep_name)], limit=1)
                        if user_by_name:
                            user_id = user_by_name.id
                            user_by_name.write({'forcemanager_id': fm_salesrep_id})
                        else:
                            # CREAR usuario
                            _logger.info("[sync_accounts] Creando nuevo usuario para '%s' (FM Rep ID=%d)", rep_name, fm_salesrep_id)
                            user_login = f"fm_{fm_salesrep_id}@example.com"
                            new_user = self.env['res.users'].create({
                                'name': rep_name,
                                'login': user_login,
                                'forcemanager_id': fm_salesrep_id,
                            })
                            user_id = new_user.id
            else:
                if rep_name:
                    user_by_name = self.env['res.users'].search([('name', '=', rep_name)], limit=1)
                    if user_by_name:
                        user_id = user_by_name.id
                    # (no creamos usuario sin ID)

            # =====================================================================
            # 3) Recargo equivalencia
            # =====================================================================
            property_account_position_id = False
            if fm_acc.get('Z_Recargo_de_equivalencia') is True:
                rec_fpos = self.env['account.fiscal.position'].search(
                    [('name', 'ilike', 'Recargo de Equivalencia')], limit=1
                )
                if rec_fpos:
                    property_account_position_id = rec_fpos.id

            # =====================================================================
            # 4) Crear/actualizar el partner principal (is_company=True)
            # =====================================================================
            vals = {
                'is_company': True,
                'forcemanager_id': fm_id,
                'forcemanager_salesrep_id': fm_salesrep_id,
                'user_id': user_id,
                'name': raw_name,
                'street': street,
                'street2': street2,
                'city': city,
                'zip': zipcode,
                'country_id': country_rec.id if country_rec else False,
                'state_id': state_rec.id if state_rec else False,
                'email': fm_acc.get('email') or "",
                'phone': fm_acc.get('phone') or "",
                'mobile': fm_acc.get('phone2') or "",
                'website': website,
                'vat': nif,
                'comercial': nombre_comercial,
                'comment': comment_html,
                'property_account_position_id': property_account_position_id,
                'forcemanager_country_id': fm_country_id,
                'forcemanager_country': fm_country_str,
            }

            #if partner:
            #    _logger.info("[sync_accounts] Actualizando partner %d (FM ID=%s)", partner.id, fm_id)
            #    partner.write(vals)
            #else:
            #    _logger.info("[sync_accounts] Creando nuevo partner (FM ID=%s)", fm_id)
            #    partner = self.env['res.partner'].create(vals)

            if partner:
                _logger.info("[sync_accounts] Actualizando partner %d (FM ID=%s)", partner.id, fm_id)
                partner.with_context(sync_from_forcemanager=True).write(vals)
            else:
                _logger.info("[sync_accounts] Creando nuevo partner (FM ID=%s)", fm_id)
                partner = self.env['res.partner'].with_context(sync_from_forcemanager=True).create(vals)

            # Y acto seguido, para marcarlo como sincronizado:
            partner.with_context(sync_from_forcemanager=True).write({'synced_with_forcemanager': True})


            # =====================================================================
            # 5) CREAR CONTACTO HIJO (si viene Z_Nombre_persona_de_contacto)
            # =====================================================================
            z_contact_name = fm_acc.get('Z_Nombre_persona_de_contacto')
            if z_contact_name:
                # Buscamos si ya existe un contacto con ese nombre y parent_id
                contact_vals = {
                    'is_company': False,
                    'parent_id': partner.id,
                    'name': z_contact_name,
                    # Reutilizamos datos del partner "account" principal
                    'phone': vals['phone'],
                    'mobile': vals['mobile'],
                    'email': vals['email'],
                    'street': vals['street'],
                    'street2': vals['street2'],
                    'city': vals['city'],
                    'zip': vals['zip'],
                    'country_id': vals['country_id'],
                    'state_id': vals['state_id'],
                    # O cualquier otro campo que quieras trasladar
                    'comment': "Contacto automático creado a través de creación de empresa."
                }
                existing_contact = self.env['res.partner'].search([
                    ('parent_id', '=', partner.id),
                    ('is_company', '=', False),
                    ('name', '=', z_contact_name),
                ], limit=1)

                if existing_contact:
                    _logger.info("[sync_accounts] Actualizando contacto hijo %d '%s'", existing_contact.id, z_contact_name)
                    existing_contact.with_context(sync_from_forcemanager=True).write(contact_vals)
                else:
                    _logger.info("[sync_accounts] Creando contacto hijo '%s' para la cuenta %d", z_contact_name, partner.id)
                    self.env['res.partner'].with_context(sync_from_forcemanager=True).create(contact_vals)

        # Guardar fecha de sync final
        self._update_last_sync_date('accounts')
        _logger.info("<<< [sync_accounts] Finalizada la sincronización de cuentas.")



    # -------------------------------------------------------------------------
    # CONTACTS
    # -------------------------------------------------------------------------
    def sync_contacts(self):
        """
        Sincroniza los contactos individuales (is_company=False) desde ForceManager.
        """
        _logger.info(">>> [sync_contacts] Iniciando sincronización de contactos (contacts)")

        last_sync = self._get_last_sync_date('contacts')
        if not last_sync:
            date_updated_str = '2025-01-01T00:00:00Z'
        else:
            tmp = fields.Datetime.to_string(last_sync)
            date_updated_str = tmp.replace(' ', 'T') + 'Z'

        where_clause = f"(dateUpdated gt '{date_updated_str}' OR dateCreated gt '{date_updated_str}')"
        endpoint_url = f"contacts?where={where_clause}"
        _logger.info("[sync_contacts] GET /api/v4/%s", endpoint_url)

        response = self.env['forcemanager.api']._perform_request(endpoint_url, method='GET')
        if not response:
            _logger.warning("[sync_contacts] Respuesta vacía o error. Abortando.")
            return

        fm_contact_list = response if isinstance(response, list) else response.get('results', [])
        _logger.info("[sync_contacts] Recibidos %d contactos desde ForceManager", len(fm_contact_list))

        for fm_ctc in fm_contact_list:
            fm_ctc_id = fm_ctc.get('id')
            try:
                fm_id = int(fm_ctc_id) if fm_ctc_id else 0
            except ValueError:
                fm_id = 0

            partner = self.env['res.partner'].search([
                ('forcemanager_id', '=', fm_id),
                ('is_company', '=', False),
            ], limit=1)

            # salesRepId => user_id
            salesrep_data = fm_ctc.get('salesRepId') or {}
            fm_salesrep_id_raw = salesrep_data.get('id')
            try:
                fm_salesrep_id = int(fm_salesrep_id_raw) if fm_salesrep_id_raw else 0
            except ValueError:
                fm_salesrep_id = 0

            rep_name = salesrep_data.get('value') or ""
            user_id = False

            if fm_salesrep_id > 0:
                user_by_fmid = self.env['res.users'].search([('forcemanager_id', '=', fm_salesrep_id)], limit=1)
                if user_by_fmid:
                    user_id = user_by_fmid.id
                else:
                    if rep_name:
                        user_by_name = self.env['res.users'].search([('name', '=', rep_name)], limit=1)
                        if user_by_name:
                            user_id = user_by_name.id
                            user_by_name.write({'forcemanager_id': fm_salesrep_id})
                        else:
                            # --- NUEVO: CREAR USUARIO SI NO EXISTE ---
                            _logger.info("[sync_contacts] Creando nuevo usuario para '%s' (FM Rep ID=%d)", rep_name, fm_salesrep_id)
                            user_login = f"fm_{fm_salesrep_id}@example.com"
                            new_user = self.env['res.users'].create({
                                'name': rep_name,
                                'login': user_login,
                                'forcemanager_id': fm_salesrep_id,
                            })
                            user_id = new_user.id
            else:
                if rep_name:
                    user_by_name = self.env['res.users'].search([('name', '=', rep_name)], limit=1)
                    if user_by_name:
                        user_id = user_by_name.id
                    else:
                        # Sin ID => no se asigna forcemanager_id
                        pass

            first_name = fm_ctc.get('firstName') or ""
            last_name = fm_ctc.get('lastName') or ""
            raw_name = (first_name + " " + last_name).strip() or "(Sin nombre)"

            # typeId => job_title
            type_data = fm_ctc.get('typeId') or {}
            job_title = type_data.get('value') or ""

            phone1 = fm_ctc.get('phone1') or ""
            phone2 = fm_ctc.get('phone2') or ""
            email = fm_ctc.get('email') or ""
            comment_html = fm_ctc.get('comment') or ""

            # Cuenta => parent_id
            account_data = fm_ctc.get('accountId') or {}
            fm_parent_id_raw = account_data.get('id')
            try:
                fm_parent_id = int(fm_parent_id_raw) if fm_parent_id_raw else 0
            except ValueError:
                fm_parent_id = 0

            parent_partner_id = False
            if fm_parent_id:
                parent_partner = self.env['res.partner'].search([
                    ('forcemanager_id', '=', fm_parent_id),
                    ('is_company', '=', True),
                ], limit=1)
                if parent_partner:
                    parent_partner_id = parent_partner.id

            # Si usan la dirección de la cuenta
            use_company_address = fm_ctc.get('UseCompanyAddress')
            if use_company_address and parent_partner_id:
                company_partner = self.env['res.partner'].browse(parent_partner_id)
                street = company_partner.street or ""
                street2 = company_partner.street2 or ""
                city = company_partner.city or ""
                zipcode = company_partner.zip or ""
                country_id = company_partner.country_id.id or False
                state_id = company_partner.state_id.id or False
            else:
                street = fm_ctc.get('address1') or ""
                street2 = fm_ctc.get('address2') or ""
                city = fm_ctc.get('city') or ""
                zipcode = fm_ctc.get('postcode') or ""

                # Buscar country (por forcemanager_id / nombre)
                cty_data = fm_ctc.get('countryId') or {}
                fm_cty_id = 0
                fm_cty_name = ""
                if isinstance(cty_data, dict):
                    raw_cid = cty_data.get('id')
                    try:
                        fm_cty_id = int(raw_cid) if raw_cid else 0
                    except ValueError:
                        fm_cty_id = 0
                    fm_cty_name = cty_data.get('value', "")

                country_id = False
                if fm_cty_id > 0:
                    ctry_rec = self.env['res.country'].search([('forcemanager_id', '=', fm_cty_id)], limit=1)
                    if ctry_rec:
                        country_id = ctry_rec.id

                if not country_id and fm_cty_name:
                    ctry_rec = self.env['res.country'].search([('name', 'ilike', fm_cty_name)], limit=1)
                    if ctry_rec:
                        country_id = ctry_rec.id

                if not country_id:
                    fallback_ctry = self.env['res.country'].search([('code', '=', 'ES')], limit=1)
                    if fallback_ctry:
                        country_id = fallback_ctry.id

                # province => buscaremos con 'ilike' region
                region = fm_ctc.get('region') or ""
                state_id = False
                if region and country_id:
                    st = self.env['res.country.state'].search([
                        ('name', 'ilike', region),
                        ('country_id', '=', country_id)
                    ], limit=1)
                    if st:
                        state_id = st.id

            vals = {
                'is_company': False,
                'forcemanager_id': fm_id,
                'forcemanager_salesrep_id': fm_salesrep_id,
                'user_id': user_id,
                'name': raw_name,
                'phone': phone1,
                'mobile': phone2,
                'email': email,
                'function': job_title,
                'comment': comment_html,
                'parent_id': parent_partner_id,

                'street': street,
                'street2': street2,
                'city': city,
                'zip': zipcode,
                'country_id': country_id,
                'state_id': state_id,
            }

            #if partner:
            #    _logger.info("[sync_contacts] Actualizando partner %d (FM ID=%s)", partner.id, fm_id)
            #    partner.write(vals)
            #else:
            #    _logger.info("[sync_contacts] Creando nuevo partner (FM ID=%s)", fm_id)
            #    partner = self.env['res.partner'].create(vals)

            _logger.info("[sync_contacts] partner.id=%d procesado correctamente.", partner.id)
            
            if partner:
                _logger.info("[sync_accounts] Actualizando partner %d (FM ID=%s)", partner.id, fm_id)
                partner.with_context(sync_from_forcemanager=True).write(vals)
            else:
                _logger.info("[sync_accounts] Creando nuevo partner (FM ID=%s)", fm_id)
                partner = self.env['res.partner'].with_context(sync_from_forcemanager=True).create(vals)

        # Y acto seguido, para marcarlo como sincronizado:
        partner.with_context(sync_from_forcemanager=True).write({'synced_with_forcemanager': True})


        self._update_last_sync_date('contacts')
        _logger.info("<<< [sync_contacts] Finalizada la sincronización de contactos.")





    # -------------------------------------------------------------------------
    # OPPORTUNITIES
    # -------------------------------------------------------------------------
    def sync_opportunities(self):
        """
        Sincroniza las oportunidades de ForceManager → Odoo (crm.lead).
        Controla todos los posibles campos nulos.
        """
        _logger.info(">>> [sync_opportunities] Iniciando sincronización de oportunidades (opportunities)")

        last_sync = self._get_last_sync_date('opportunities')
        if not last_sync:
            date_filter_str = '2025-01-01T00:00:00Z'
        else:
            tmp = fields.Datetime.to_string(last_sync)
            date_filter_str = tmp.replace(' ', 'T') + 'Z'

        where_clause = f"(dateUpdated > '{date_filter_str}' OR dateCreated > '{date_filter_str}')"
        endpoint_url = f"opportunities?where={where_clause}"
        _logger.info("[sync_opportunities] GET /api/v4/%s", endpoint_url)

        response = self.env['forcemanager.api']._perform_request(endpoint_url, method='GET')
        if not response:
            _logger.warning("[sync_opportunities] Respuesta vacía o error. Abortando.")
            return

        fm_opp_list = response if isinstance(response, list) else response.get('results', [])
        _logger.info("[sync_opportunities] Recibidas %d oportunidades desde ForceManager", len(fm_opp_list))

        for fm_opp in fm_opp_list:
            # ---------------------------------------------------------------------
            # 1) ID de ForceManager => forcemanager_opportunity_id
            # ---------------------------------------------------------------------
            fm_opp_id_raw = fm_opp.get('id')
            try:
                fm_opp_id = int(fm_opp_id_raw) if fm_opp_id_raw else 0
            except (TypeError, ValueError):
                fm_opp_id = 0

            # Buscar lead en Odoo (si ya existe)
            lead = self.env['crm.lead'].search([
                ('forcemanager_opportunity_id', '=', fm_opp_id)
            ], limit=1)

            # ---------------------------------------------------------------------
            # 2) Nombre, comentarios
            # ---------------------------------------------------------------------
            raw_name = fm_opp.get('reference') or "(Opp sin nombre)"
            comment = fm_opp.get('comments') or ""

            # ---------------------------------------------------------------------
            # 3) Moneda (currencyId)
            # ---------------------------------------------------------------------
            currency_data = fm_opp.get('currencyId') or {}
            currency_fm = currency_data.get('value') or ""  # p.ej. "euro"

            # ---------------------------------------------------------------------
            # 4) statusId => etapa
            # ---------------------------------------------------------------------
            status_data = fm_opp.get('statusId') or {}
            fm_stage_name = status_data.get('value') or ""  # p.ej. "En negociación"

            # ---------------------------------------------------------------------
            # 5) Probabilidad (salesProbability => 0..10 => 0..100)
            # ---------------------------------------------------------------------
            prob_fm = fm_opp.get('salesProbability', 0)
            probability = prob_fm * 10.0

            # ---------------------------------------------------------------------
            # 6) Fecha de previsión de cierre (salesForecastDate)
            # ---------------------------------------------------------------------
            date_deadline = False
            close_str = fm_opp.get('salesForecastDate')
            if close_str:
                try:
                    close_str_clean = close_str.rstrip("Z")
                    date_deadline = datetime.strptime(close_str_clean, '%Y-%m-%dT%H:%M:%S').date()
                except ValueError as e:
                    _logger.warning("[sync_opportunities] Error parseando salesForecastDate='%s': %s", close_str, e)

            # ---------------------------------------------------------------------
            # 7) Importe previsto (total)
            # ---------------------------------------------------------------------
            total = fm_opp.get('total', 0.0)

            # ---------------------------------------------------------------------
            # 8) Comercial => forcemanager_salesrep_id + user_id
            # ---------------------------------------------------------------------
            salesrep_data = fm_opp.get('salesRepId') or {}
            fm_salesrep_id_raw = salesrep_data.get('id')
            try:
                fm_salesrep_id = int(fm_salesrep_id_raw) if fm_salesrep_id_raw else 0
            except (TypeError, ValueError):
                fm_salesrep_id = 0

            rep_name = salesrep_data.get('value') or ""
            user_id = False
            if rep_name:
                user_rec = self.env['res.users'].search([('name', '=', rep_name)], limit=1)
                if user_rec:
                    user_id = user_rec.id

            # ---------------------------------------------------------------------
            # 9) Vinculación con la cuenta => accountId1
            # ---------------------------------------------------------------------
            account_data = fm_opp.get('accountId1') or {}
            fm_account_id_raw = account_data.get('id')
            try:
                fm_account_id = int(fm_account_id_raw) if fm_account_id_raw else 0
            except (TypeError, ValueError):
                fm_account_id = 0

            partner_id = False
            if fm_account_id:
                partner_rec = self.env['res.partner'].search([
                    ('forcemanager_id', '=', fm_account_id),
                    ('is_company', '=', True),
                ], limit=1)
                if partner_rec:
                    partner_id = partner_rec.id

            # ---------------------------------------------------------------------
            # 10) Z_Que_marcas_de_vaper_vende => lista
            # ---------------------------------------------------------------------
            fm_brands_list = fm_opp.get('Z_Que_marcas_de_vaper_vende') or []
            # Si es None => se convierte en lista vacía
            brand_values = []
            if isinstance(fm_brands_list, list):
                brand_values = [brand.get('value', '') for brand in fm_brands_list]
            # join
            brands_str = ", ".join(b for b in brand_values if b)

            # ---------------------------------------------------------------------
            # 11) Construir vals
            # ---------------------------------------------------------------------
            vals = {
                'forcemanager_opportunity_id': fm_opp_id,
                'forcemanager_salesrep_id': fm_salesrep_id,
                'name': raw_name,
                'description': comment,
                'probability': probability,
                'expected_revenue': total,
                'date_deadline': date_deadline,
                'partner_id': partner_id,
                'user_id': user_id,
                # Ejemplo: si tuvieras un campo x_vaper_brands, se lo asignas:
                # 'x_vaper_brands': brands_str,
            }

            # Etapa => stage_id
            stage_rec = self.env['crm.stage'].search([('name', '=', fm_stage_name)], limit=1)
            if stage_rec:
                vals['stage_id'] = stage_rec.id

            # 12) Crear o actualizar la Oportunidad (crm.lead)
            if lead:
                _logger.info("[sync_opportunities] Actualizando crm.lead ID=%d (FM Opp ID=%s)", lead.id, fm_opp_id)
                lead.with_context(sync_from_forcemanager=True).write(vals)
            else:
                _logger.info("[sync_opportunities] Creando nuevo crm.lead (FM Opp ID=%s)", fm_opp_id)
                lead = self.env['crm.lead'].with_context(sync_from_forcemanager=True).create(vals)

            # 13) Marcar la oportunidad como sincronizada
            lead.with_context(sync_from_forcemanager=True).write({'synced_with_forcemanager': True})
            _logger.info("[sync_opportunities] lead.id=%d procesada con éxito.", lead.id)

        # 14) Actualizar fecha de última sincronización
        self._update_last_sync_date('opportunities')
        _logger.info("<<< [sync_opportunities] Finalizada la sincronización de oportunidades.")


        
    # -------------------------------------------------------------------------
    # ORDERS
    # -------------------------------------------------------------------------
    def sync_orders(self):
        """
        Sincroniza los 'Sales' (pedidos) de ForceManager con los pedidos (sale.order) de Odoo.
        - Localiza cada pedido por forcemanager_id
        - Crea o actualiza en Odoo
        - Maneja 'deleted' y 'dateDeleted' para cancelar el pedido en Odoo
        - Lee 'Z_Entrega_mismo_comercial' ("Si"/"No") y lo guarda en x_entrega_mismo_comercial ('si'/'no')
        - Guarda el campo 'status' de ForceManager en forcemanager_status (si existe)
        """
        _logger.info(">>> [sync_orders] Iniciando sincronización de pedidos (orders)")

        last_sync = self._get_last_sync_date('orders')
        if not last_sync:
            # Si nunca se ha sincronizado antes, partimos de una fecha fija
            date_updated_str = '2025-01-01T00:00:00Z'
        else:
            # Convertimos el campo de tipo datetime de Odoo a la cadena con 'T' y sufijo 'Z'
            tmp = fields.Datetime.to_string(last_sync)
            date_updated_str = tmp.replace(' ', 'T') + 'Z'

        # Aquí usamos date_updated_str en el filtro con 'gt' (greater than)
        where_clause = f"(dateUpdated gt '{date_updated_str}' OR dateCreated gt '{date_updated_str}')"
        endpoint_url = f"sales?where={where_clause}"
        _logger.info("[sync_orders] GET /api/v4/%s", endpoint_url)

        # Petición a ForceManager
        response = self.env['forcemanager.api']._perform_request(endpoint_url, method='GET')
        if not response:
            _logger.warning("[sync_orders] Respuesta vacía o error. Abortando.")
            return

        fm_order_list = response if isinstance(response, list) else response.get('results', [])
        _logger.info("[sync_orders] Recibidos %d pedidos desde ForceManager", len(fm_order_list))

        for fm_order in fm_order_list:
            fm_id = fm_order.get('id')  # p.ej. 123
            if not fm_id:
                continue
            
            try:
                fm_id_int = int(fm_id)
            except ValueError:
                fm_id_int = 0

            # 1) Buscar si ya existe el pedido en Odoo por forcemanager_id
            order = self.env['sale.order'].search([('forcemanager_id', '=', fm_id_int)], limit=1)

            # 2) Revisar si ForceManager marcó 'deleted' => anular pedido en Odoo
            is_deleted = fm_order.get('deleted') is True
            date_deleted = fm_order.get('dateDeleted')  # p.ej. "2025-01-31T10:00:00Z"
            if is_deleted or date_deleted:
                if order and order.state not in ('cancel', 'done'):
                    _logger.info("[sync_orders] FM Order ID=%s está 'deleted'. Cancelando en Odoo.", fm_id_int)
                    order.action_cancel()
                continue  # No crear/actualizar más

            # 3) Identificar al cliente (partner_id)
            fm_account = fm_order.get('accountId')
            partner_id = False
            if fm_account and fm_account.get('id'):
                try:
                    fm_account_id_int = int(fm_account['id'])
                except ValueError:
                    fm_account_id_int = 0

                partner_rec = self.env['res.partner'].search([
                    ('forcemanager_id', '=', fm_account_id_int),
                    ('is_company', '=', True),
                ], limit=1)
                if partner_rec:
                    partner_id = partner_rec.id

            # 4) Fecha del pedido
            date_order = False
            fm_date_str = fm_order.get('dateCreated')  # "2025-01-21T10:00:00Z"
            if fm_date_str:
                try:
                    fm_date_str = fm_date_str.rstrip("Z")
                    date_order_dt = datetime.strptime(fm_date_str, '%Y-%m-%dT%H:%M:%S')
                    date_order = fields.Datetime.to_string(date_order_dt)
                except ValueError as e:
                    _logger.warning("[sync_orders] No se pudo parsear dateCreated='%s': %s", fm_date_str, e)

            # 5) Moneda
            currency_name = fm_order.get('currencyId', {}).get('value')
            currency_id = False
            if currency_name:
                currency_rec = self.env['res.currency'].search([('name', '=', currency_name)], limit=1)
                if currency_rec:
                    currency_id = currency_rec.id

            # 6) Comercial (salesRepId => user_id)
            user_id = False
            fm_salesrep = fm_order.get('salesRepId')
            if fm_salesrep and fm_salesrep.get('value'):
                rep_name = fm_salesrep['value']
                user_rec = self.env['res.users'].search([('name', '=', rep_name)], limit=1)
                if user_rec:
                    user_id = user_rec.id
                # Si quieres crear usuario si no existe, replica la lógica de sync_accounts()

            # 7) Campo 'Z_Entrega_mismo_comercial' => x_entrega_mismo_comercial
            fm_entrega = fm_order.get('Z_Entrega_mismo_comercial')  # "Si" / "No"
            x_entrega = False
            if fm_entrega == "Si":
                x_entrega = 'si'
            elif fm_entrega == "No":
                x_entrega = 'no'

            # 8) forcemanager_status si lo manda ForceManager
            fm_status = fm_order.get('status') or ""  # Ajusta la clave si es otra

            # 9) Montar los vals para sale.order
            vals_order = {
                'forcemanager_id': fm_id_int,
                'partner_id': partner_id,
                'date_order': date_order,
                'currency_id': currency_id,
                'user_id': user_id,
                'partner_invoice_id': partner_id,
                'partner_shipping_id': partner_id,
                'x_entrega_mismo_comercial': x_entrega,
                'forcemanager_status': fm_status,
            }

            if order:
                _logger.info("[sync_orders] Actualizando pedido %d (FM ID=%s)", order.id, fm_id_int)
                order.write(vals_order)
            else:
                _logger.info("[sync_orders] Creando nuevo sale.order (FM ID=%s)", fm_id_int)
                order = self.env['sale.order'].create(vals_order)

            # 10) Manejar líneas del pedido
            fm_lines = fm_order.get('lines', [])
            self._sync_order_lines(order, fm_lines)

            # 11) Marcamos como sincronizado
            order.synced_with_forcemanager = True
            _logger.info("[sync_orders] sale.order.id=%d procesado con éxito.", order.id)

        # 12) Actualizar fecha de última sincronización
        self._update_last_sync_date('orders')
        _logger.info("<<< [sync_orders] Finalizada la sincronización de pedidos.")



    def _sync_order_lines(self, order, fm_lines):
        """
        Crea/actualiza líneas del pedido segun la info de ForceManager.
        Ejemplo: si no tienes forcemanager_line_id, puedes hacer un "borrar y crear"
        """
        # Enfoque sencillo: borramos y creamos todas las líneas
        order.order_line.unlink()

        for line_data in fm_lines:
            fm_prod_id = line_data.get('productId')
            product_id = self._find_odoo_product_by_fm_id(fm_prod_id)

            price_unit = line_data.get('unitPrice', 0.0)
            quantity = line_data.get('quantity', 1)
            product_name = line_data.get('productName', 'Línea sin producto')

            line_vals = {
                'order_id': order.id,
                'product_id': product_id,
                'product_uom_qty': quantity,
                'price_unit': price_unit,
                'name': product_name,
        }
        self.env['sale.order.line'].create(line_vals)


    def _find_odoo_product_by_fm_id(self, fm_prod_id):
        """Busca product.product con forcemanager_id=fm_prod_id"""
        if not fm_prod_id:
            return False
        try:
            fm_prod_id_int = int(fm_prod_id)
        except ValueError:
            return False

        product = self.env['product.product'].search([('forcemanager_id','=',fm_prod_id_int)], limit=1)
        return product.id if product else False
    
    def sync_products(self):
        """
        Descarga products desde ForceManager y ACTUALIZA en Odoo únicamente
        los que ya existan (basados en forcemanager_id).
        No crea productos nuevos ni modifica stock en Odoo.

        - model => name
        - price => list_price
        - cost => standard_price
        - categoryId => se busca en product.category.forcemanager_id
        - Se ignora cualquier 'stock' que llegue de FM.
        """
        _logger.info(">>> [sync_products] Iniciando sincronización de productos (products)")

        last_sync = self._get_last_sync_date('products')
        if not last_sync:
            date_updated_str = '2025-01-01T00:00:00Z'
        else:
            tmp = fields.Datetime.to_string(last_sync)
            date_updated_str = tmp.replace(' ', 'T') + 'Z'

        where_clause = f"(dateUpdated gt '{date_updated_str}' OR dateCreated gt '{date_updated_str}')"
        endpoint_url = f"products?where={where_clause}"
        _logger.info("[sync_products] GET /api/v4/%s", endpoint_url)

        response = self.env['forcemanager.api']._perform_request(endpoint_url, method='GET')
        if not response:
            _logger.warning("[sync_products] Respuesta vacía o error. Abortando.")
            return

        fm_product_list = response if isinstance(response, list) else response.get('results', [])
        _logger.info("[sync_products] Recibidos %d productos desde ForceManager", len(fm_product_list))

        ProductObj = self.env['product.product']
        CategoryObj = self.env['product.category']

        for fm_prod in fm_product_list:
            fm_prod_id_raw = fm_prod.get('id')
            if not fm_prod_id_raw:
                continue

            try:
                fm_prod_id = int(fm_prod_id_raw)
            except ValueError:
                fm_prod_id = 0

            # 1) Buscamos el producto existente en Odoo
            product = ProductObj.search([('forcemanager_id', '=', fm_prod_id)], limit=1)
            if not product:
                # No creamos productos nuevos
                _logger.info("[sync_products] (FM ID=%s) No existe en Odoo => se omite la creación.", fm_prod_id)
                continue

            # 2) Campos relevantes (ignoramos 'stock', solo tomamos model, description, price, cost, categoryId)
            model_value = fm_prod.get('model') or ""
            desc_value = fm_prod.get('description') or ""
            price_value = fm_prod.get('price', 0.0)
            cost_value = fm_prod.get('cost', 0.0)
            # fm_prod.get('stock') se ignora

            # Nombre del producto
            name = model_value.strip() or desc_value.strip() or "(Sin nombre)"

            # 3) Determinamos la categoría
            fm_cat_obj = fm_prod.get('categoryId')
            categ_id = product.categ_id.id  # Mantenemos la categoría actual si no hay match
            if isinstance(fm_cat_obj, int):
                # ForceManager puede enviar categoryId como int directo
                cat_str = str(fm_cat_obj)
                existing_cat = CategoryObj.search([('forcemanager_id', '=', cat_str)], limit=1)
                if existing_cat:
                    categ_id = existing_cat.id
            elif isinstance(fm_cat_obj, dict):
                # Otras veces es un objeto {"id": 12, "value": "..."}, comprobamos id
                raw_id = fm_cat_obj.get('id')
                if raw_id:
                    cat_str = str(raw_id)
                    existing_cat = CategoryObj.search([('forcemanager_id', '=', cat_str)], limit=1)
                    if existing_cat:
                        categ_id = existing_cat.id
                    else:
                        _logger.info("[sync_products] Category FM ID=%s no se encuentra en Odoo => se omite.", cat_str)

            # 4) Construimos los vals para actualizar en Odoo
            vals = {
                'name': name,
                'list_price': price_value,
                'standard_price': cost_value,
                'synced_with_forcemanager': True,
                'categ_id': categ_id,
            }
            if desc_value:
                vals['description_sale'] = desc_value

            _logger.info("[sync_products] Actualizando product.product ID=%d (FM ID=%s)", product.id, fm_prod_id)
            # Use context to avoid triggering re-sync logic
            product.with_context(sync_from_forcemanager=True).write(vals)

        self._update_last_sync_date('products')
        _logger.info("<<< [sync_products] Finalizada la sincronización de productos.")
        
    # -------------------------------------------------------------------------
    # Auxiliares
    # -------------------------------------------------------------------------
    def _get_last_sync_date(self, entity):
        return self.env['forcemanager.api'].get_last_sync_date(entity)

    def _update_last_sync_date(self, entity):
        self.env['forcemanager.api'].set_last_sync_date(entity)
        _logger.info("[_update_last_sync_date] Fecha de sync actualizada para '%s'.", entity)
