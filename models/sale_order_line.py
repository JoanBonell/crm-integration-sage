from odoo import fields, models, api
import logging

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    forcemanager_line_id = fields.Char(copy=False)

