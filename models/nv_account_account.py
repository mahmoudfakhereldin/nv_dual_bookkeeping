import logging
from datetime import date as _date
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountAccount(models.Model):
    _inherit = 'account.account'

    sap_code = fields.Char(string='SAP Code')