# models/opportunity_extension.py
from odoo import fields, models, api
import logging


_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    forcemanager_id = fields.Char(string='ForceManager ID', copy=False, index=True)
    forcemanager_stage = fields.Char(string='ForceManager Stage')
    forcemanager_opportunity_id = fields.Integer(string='FM Opportunity ID', copy=False, index=True)
    forcemanager_salesrep_id = fields.Integer(string='FM SalesRep ID', copy=False, index=True)
    synced_with_forcemanager = fields.Boolean(string='Synced with ForceManager', default=False)
    
    @api.model
    def create(self, vals):
        if not self.env.context.get('sync_from_forcemanager'):
            vals['synced_with_forcemanager'] = False
        lead = super(CrmLead, self).create(vals)
        return lead

    def write(self, vals):
        res = super(CrmLead, self).write(vals)
        if not self.env.context.get('sync_from_forcemanager'):
            self.filtered(lambda l: l.synced_with_forcemanager).write({'synced_with_forcemanager': False})
        return res

    
