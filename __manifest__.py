{
    'name': 'Sage Sales CRM Integration',
    'version': '1.0.0.0',
    'category': 'Sales/CRM',
    'summary': 'Integración con Sage Sales Management',
    'description': """
    Este módulo integra Sage Sales CRM con Odoo. Para usarlo debemos configurar las claves de API dentro de Ajustes -> Técnico -> Parámetros del Sistema.
    En este punto, añadir:
    forcemanager_integration.public_key = ``
    forcemanager_integration.private_key = ``
    forcemanager_integration.base_url (opcional, por defecto https://api.forcemanager.net). 
    """,
    'author': 'Joan Bonell Ruiz',
    'maintainer': 'Joan Bonell Ruiz',
    'website': 'https://www.bonell.dev',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale',
        'crm',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/forcemanager_cron.xml',
        'views/res_partner_view.xml',
        'views/crm_lead_view.xml',
        'views/res_users_view_inherit.xml',
        'views/sale_order_view_inherit_forcemanager.xml',
        'views/product_template_view_inherit_forcemanager.xml',
        'views/product_category_view_inherit_forcemanager.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
