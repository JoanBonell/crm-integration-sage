{
    'name': 'ForceManager Integration',
    'version': '15.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Integración bidireccional con ForceManager',
    'description': """
Este módulo integra Odoo con ForceManager, leyendo claves desde
'ir.config_parameter' en lugar de dotenv.
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
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
