# models/order_extension.py
from odoo import fields, models

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    forcemanager_id = fields.Char(string='ForceManager ID', copy=False, index=True)
    forcemanager_status = fields.Char(string='ForceManager Status')
    synced_with_forcemanager = fields.Boolean(string='Synced with ForceManager', default=False)
    x_entrega_mismo_comercial = fields.Selection(selection=[('si', 'Si'), ('no', 'No')],
        string="Entrega mismo comercial")