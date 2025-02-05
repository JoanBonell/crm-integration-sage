# models/product_template.py

from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def write(self, vals):
        """
        Sobrescribimos 'write' para que, si se actualiza algún campo relevante
        (por ejemplo: name, lista de precios, coste, categoría...), 
        el producto deje de considerarse sincronizado (synced_with_forcemanager=False).

        EXCEPCIÓN: si la actualización viene de la propia sincronización ForceManager → Odoo
        (e.g. durante la sync), podemos usar un contexto especial ('sync_from_forcemanager')
        para no reinvertir el flag y evitar bucles.
        """

        # Guardamos el resultado del super() primero
        res = super().write(vals)

        # Comprobamos si se está llamando con un contexto especial
        # que indique que viene "desde ForceManager" (para no caer en bucles)
        if not self.env.context.get('sync_from_forcemanager'):
            # Definimos los campos que si cambian, queremos marcar 'synced_with_forcemanager' = False
            campos_relevantes = {'name', 'list_price', 'standard_price', 'default_code', 
                                 'categ_id', 'uom_id', 'uom_po_id', 'active'}

            # Si alguno de esos campos está en vals, es que ha cambiado
            if campos_relevantes.intersection(vals.keys()):
                for product_tmpl in self:
                    if product_tmpl.synced_with_forcemanager:
                        product_tmpl.synced_with_forcemanager = False

        return res
