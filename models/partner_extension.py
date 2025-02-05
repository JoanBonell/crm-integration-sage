# models/partner_extension.py
from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    forcemanager_id = fields.Integer(string='ForceManager ID', copy=False, index=True)
    forcemanager_salesrep_id = fields.Integer(string= 'FM SalesRep ID', copy=False, index=True)
    forcemanager_country_id = fields.Integer(string='FM Country ID', copy=False, index=True)
    forcemanager_country = fields.Char(string='FM Country Str', copy=False, index=True)
    synced_with_forcemanager = fields.Boolean(string='Synced with ForceManager', default=False)
    
    
    
    @api.model
    def create(self, vals):
        """
        Sobrescribimos create para que, si es una creación manual en Odoo
        (no viene de ForceManager), comience con `synced_with_forcemanager=False`.
        """
        if not self.env.context.get('sync_from_forcemanager'):
            vals['synced_with_forcemanager'] = False
        partner = super().create(vals)
        return partner

    def write(self, vals):
        """
        Sobrescribimos write para que, si se actualiza cualquier campo en Odoo
        (y no viene del contexto sync_from_forcemanager), se ponga
        synced_with_forcemanager=False.
        """
        res = super(ResPartner, self).write(vals)

        if not self.env.context.get('sync_from_forcemanager'):
            # Marcamos como no sincronizado solo los que estaban True
            self.filtered(lambda p: p.synced_with_forcemanager).write({'synced_with_forcemanager': False})
            _logger.info("[ResPartner] Marcados como 'no sincronizados' (synced_with_forcemanager=False) tras update.")
        return res
