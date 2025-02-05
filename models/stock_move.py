# models/stock_move.py

from odoo import models, fields

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        """
        Sobrescribimos la confirmación final de los movimientos de stock.
        Tras realizar la operación estándar, para cada move afectado,
        marcamos su 'product_tmpl_id' con synced_with_forcemanager=False,
        a menos que venga desde la propia sincronización.
        """
        moves = super()._action_done(cancel_backorder=cancel_backorder)

        if not self.env.context.get('sync_from_forcemanager'):
            for move in moves:
                # Obtenemos la plantilla
                product_tmpl = move.product_id.product_tmpl_id
                if product_tmpl.synced_with_forcemanager:
                    product_tmpl.synced_with_forcemanager = False

        return moves
