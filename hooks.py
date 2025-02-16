# my_module/hooks.py

from odoo import api, SUPERUSER_ID

def post_init_hook(cr, registry):
    """
    Esta función se ejecuta 1 sola vez
    cuando se instala el módulo.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    # 1) Sincronizamos países de forcemanager con los de Odoo
    env['res.country'].sync_countries_from_forcemanager()
    # 2) Sincronizamos las categorías hacia forcemanager
    env['product.category'].sync_categories_to_forcemanager_on_init()
    # 3) Exportamos todos los productos hacia forcemanager
    #env['product.template'].export_all_products_to_forcemanager()
    # 3) Importar empresas de forcemanager hacia odoo
    #env['forcemanager.import'].import_companies_from_forcemanager()
    # 4) Importar contactos de forcemanager hacia odoo
    #env['forcemanager.import'].import_contacts_from_forcemanager()
    # 5) Importar oportunidades de forcemanager hacia odoo
    #env['forcemanager.import'].import_opportunities_from_forcemanager()
