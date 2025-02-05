from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    forcemanager_id = fields.Integer(
        string="ForceManager ID",
        help="ID del usuario en ForceManager"
    )
