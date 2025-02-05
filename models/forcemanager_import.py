# forcemanager_import.py
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class ForceManagerImport(models.TransientModel):
    """
    Modelo auxiliar para importar datos desde ForceManager a Odoo,
    aplicando la lógica de "no sobrescribir si ya existe con el mismo ID",
    "actualizar si coincide un campo clave pero forcemanager_id está vacío",
    "crear nuevo si no coincide nada".
    """
    _name = 'forcemanager.import'
    _description = 'Importaciones ForceManager → Odoo (Empresas, Contactos, Oportunidades)'

    @api.model
    def import_companies_from_forcemanager(self):
        """
        Importar 'Empresas' desde /accounts de ForceManager:
        1) Si ya existe partner con forcemanager_id=fm_id => NO sobreescribir.
        2) Si coincide NIF (vat) y forcemanager_id=False => actualizarlo, asignar forcemanager_id.
        3) Si no existe ninguno => crear partner nuevo con synced_with_forcemanager=True.
        """
        _logger.info("Iniciando import_companies_from_forcemanager()...")

        response = self.env['forcemanager.api']._perform_request('accounts', method='GET')
        if not response:
            _logger.warning("No hay respuesta o error en /accounts")
            return

        fm_account_list = response if isinstance(response, list) else response.get('results', [])
        _logger.info("Recibidos %d registros de ForceManager (accounts).", len(fm_account_list))

        for fm_acc in fm_account_list:
            fm_id = fm_acc.get('id')                 # ID de ForceManager
            nif = (fm_acc.get('Z_nif') or "").strip() # Ejemplo: campo 'Z_nif' en ForceManager
            name = fm_acc.get('name') or "(Sin nombre)"

            # 1) Si existe partner con forcemanager_id = fm_id => NO tocar
            if fm_id:
                existing_fm_id = self.env['res.partner'].search([
                    ('forcemanager_id', '=', fm_id),
                    ('is_company', '=', True),
                ], limit=1)
                if existing_fm_id:
                    _logger.info("Socio [FM ID=%s] ya existe (ID=%d). Saltando...", fm_id, existing_fm_id.id)
                    continue

            # 2) Si coincide NIF y forcemanager_id vacío => actualizar
            existing_by_nif = False
            if nif:
                existing_by_nif = self.env['res.partner'].search([
                    ('vat', '=', nif),
                    ('is_company', '=', True),
                ], limit=1)
                if existing_by_nif and not existing_by_nif.forcemanager_id:
                    _logger.info("Encontrado partner con NIF=%s (ID=%d) sin forcemanager_id. Actualizando...", 
                                 nif, existing_by_nif.id)
                    # Actualizamos (por ejemplo, nombre, forcemanager_id)
                    vals_update = {
                        'name': name,
                        'forcemanager_id': fm_id or False,
                        'synced_with_forcemanager': True,
                        # Mapea más campos aquí (phone, city...) si quieres.
                    }
                    existing_by_nif.write(vals_update)
                    continue
                elif existing_by_nif:
                    # Si existe con el mismo NIF pero YA tiene un forcemanager_id => no tocamos
                    _logger.info("Encontrado partner con NIF=%s (ID=%d) pero ya con forcemanager_id=%s. Saltamos.",
                                 nif, existing_by_nif.id, existing_by_nif.forcemanager_id)
                    continue

            # 3) Si no coincide => creamos nuevo
            new_vals = {
                'is_company': True,
                'forcemanager_id': fm_id or False,
                'name': name,
                'vat': nif,
                'synced_with_forcemanager': True,
                # Mapea más campos (phone, city...) si procede
            }
            new_partner = self.env['res.partner'].create(new_vals)
            _logger.info("Creado nuevo partner ID=%d con FM ID=%s / NIF=%s", 
                         new_partner.id, fm_id, nif)

        _logger.info("Finalizado import_companies_from_forcemanager().")


    @api.model
    def import_contacts_from_forcemanager(self):
        """
        Importar 'Contactos' (res.partner con is_company=False) desde /contacts de ForceManager:
        1) Si ya existe partner con forcemanager_id => no tocar.
        2) Si coincide 'email' y forcemanager_id=False => actualizar (asignar ID FM).
        3) Si no => crear nuevo partner con synced_with_forcemanager=True.
        """
        _logger.info("Iniciando import_contacts_from_forcemanager()...")

        response = self.env['forcemanager.api']._perform_request('contacts', method='GET')
        if not response:
            _logger.warning("No hay respuesta o error en /contacts")
            return

        fm_contact_list = response if isinstance(response, list) else response.get('results', [])
        _logger.info("Recibidos %d registros de ForceManager (contacts).", len(fm_contact_list))

        for fm_ctc in fm_contact_list:
            fm_id = fm_ctc.get('id')        # ID ForceManager
            email = (fm_ctc.get('email') or "").strip()
            first_name = fm_ctc.get('firstName') or ""
            last_name = fm_ctc.get('lastName') or ""
            full_name = (first_name + " " + last_name).strip() or "(Sin nombre)"

            # 1) Si ya existe un partner con forcemanager_id => no tocar
            if fm_id:
                existing_fm_id = self.env['res.partner'].search([
                    ('forcemanager_id', '=', fm_id),
                    ('is_company', '=', False),
                ], limit=1)
                if existing_fm_id:
                    _logger.info("Contacto [FM ID=%s] ya existe (ID=%d). Saltando...", fm_id, existing_fm_id.id)
                    continue

            # 2) Si coincide email y forcemanager_id vacío => actualizar
            existing_by_email = False
            if email:
                existing_by_email = self.env['res.partner'].search([
                    ('email','=', email),
                    ('is_company','=', False),
                ], limit=1)
                if existing_by_email and not existing_by_email.forcemanager_id:
                    _logger.info("Contacto con email=%s (ID=%d) sin forcemanager_id. Actualizando...",
                                 email, existing_by_email.id)
                    vals_update = {
                        'name': full_name,
                        'forcemanager_id': fm_id or False,
                        'synced_with_forcemanager': True,
                        # Añade más campos si lo deseas (phone, etc.)
                    }
                    existing_by_email.write(vals_update)
                    continue
                elif existing_by_email:
                    _logger.info("Contacto con email=%s (ID=%d) ya tiene forcemanager_id=%s. Saltamos.",
                                 email, existing_by_email.id, existing_by_email.forcemanager_id)
                    continue

            # 3) Crear uno nuevo
            vals_create = {
                'is_company': False,
                'forcemanager_id': fm_id or False,
                'name': full_name,
                'email': email,
                'synced_with_forcemanager': True,
            }
            new_contact = self.env['res.partner'].create(vals_create)
            _logger.info("Creado contacto ID=%d, FM ID=%s, email=%s", new_contact.id, fm_id, email)

        _logger.info("Finalizado import_contacts_from_forcemanager().")


    @api.model
    def import_opportunities_from_forcemanager(self):
        """
        Importar 'Oportunidades' (crm.lead) desde /opportunities:
        1) Si ya existe lead con forcemanager_id => no sobreescribir.
        2) Si coincide 'name' y forcemanager_id=False => actualizar.
        3) En caso contrario => crear nueva con synced_with_forcemanager=True.
        """
        _logger.info("Iniciando import_opportunities_from_forcemanager()...")

        response = self.env['forcemanager.api']._perform_request('opportunities', method='GET')
        if not response:
            _logger.warning("No hay respuesta o error en /opportunities")
            return

        fm_opp_list = response if isinstance(response, list) else response.get('results', [])
        _logger.info("Recibidos %d registros de ForceManager (opportunities).", len(fm_opp_list))

        for fm_opp in fm_opp_list:
            fm_id = fm_opp.get('id')     # ID ForceManager
            ref_name = fm_opp.get('reference') or "(Opp sin nombre)"

            # 1) Si hay un lead con forcemanager_id => no tocar
            if fm_id:
                existing_fm = self.env['crm.lead'].search([
                    ('forcemanager_id','=', fm_id)
                ], limit=1)
                if existing_fm:
                    _logger.info("Oportunidad [FM ID=%s] ya existe (ID=%d). Saltando...", fm_id, existing_fm.id)
                    continue

            # 2) Si coincide name y forcemanager_id vacío => actualizar
            existing_by_name = self.env['crm.lead'].search([
                ('name','=', ref_name),
                ('forcemanager_id','=', False),
            ], limit=1)
            if existing_by_name:
                _logger.info("Oportunidad con name='%s' (ID=%d) sin forcemanager_id. Actualizando...",
                             ref_name, existing_by_name.id)
                vals_update = {
                    'forcemanager_id': fm_id or False,
                    'synced_with_forcemanager': True,
                    # Mapea más campos que quieras (probability, user_id...) si quieres
                }
                existing_by_name.write(vals_update)
                continue

            # 3) Crear una nueva
            vals_create = {
                'name': ref_name,
                'forcemanager_id': fm_id or False,
                'synced_with_forcemanager': True,
            }
            new_lead = self.env['crm.lead'].create(vals_create)
            _logger.info("Creada oportunidad ID=%d con FM ID=%s, nombre='%s'", new_lead.id, fm_id, ref_name)

        _logger.info("Finalizado import_opportunities_from_forcemanager().")
