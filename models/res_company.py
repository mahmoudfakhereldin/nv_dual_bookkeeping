import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    official_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Official Company',
        domain="[('id', '!=', id)]",
        copy=False,
        help=(
            "If set, all Official transactions posted in this company will be "
            "automatically mirrored to the selected company, which acts as the "
            "Official Books ledger."
        ),
    )

    # Inverse of official_company_id — used as the depends trigger so that
    # when any company points to (or stops pointing to) this company, Odoo
    # automatically invalidates and recomputes is_official_company here.
    mirror_source_company_ids = fields.One2many(
        comodel_name='res.company',
        inverse_name='official_company_id',
        string='Mirror Source Companies',
        readonly=True,
    )

    is_official_company = fields.Boolean(
        string='Is Official Company',
        compute='_compute_is_official_company',
        store=True,
        help=(
            "Automatically set to True when at least one other company designates "
            "this company as its Official Mirror Company. Used to display warnings "
            "and optionally block direct manual posting."
        ),
    )

    @api.depends('mirror_source_company_ids')
    def _compute_is_official_company(self):
        """
        A company is the 'Official Company' when at least one other company
        has selected it as their official_company_id (mirror_source_company_ids
        is non-empty).  Depending on the One2many inverse means Odoo correctly
        invalidates this field on the TARGET company whenever any source
        company's official_company_id changes.
        """
        for company in self:
            company.is_official_company = bool(company.mirror_source_company_ids)

    # -------------------------------------------------------------------------
    # Invoice Layout — per-company visibility settings
    # -------------------------------------------------------------------------

    # Official invoices
    official_show_header_logo = fields.Boolean(
        string='[Official] Show Header Logo', default=True,
    )
    official_show_company_details = fields.Boolean(
        string='[Official] Show Company Details', default=True,
    )
    official_show_company_vat = fields.Boolean(
        string='[Official] Show Company VAT', default=True,
    )
    official_show_customer_vat = fields.Boolean(
        string='[Official] Show Customer VAT', default=True,
    )
    official_show_customer_email = fields.Boolean(
        string='[Official] Show Customer Email', default=False,
    )
    official_show_customer_phone = fields.Boolean(
        string='[Official] Show Customer Phone', default=False,
    )
    official_show_footer = fields.Boolean(
        string='[Official] Show Footer', default=True,
    )

    # Non-Official invoices
    non_official_show_header_logo = fields.Boolean(
        string='[Non-Official] Show Header Logo', default=True,
    )
    non_official_show_company_details = fields.Boolean(
        string='[Non-Official] Show Company Details', default=True,
    )
    non_official_show_company_vat = fields.Boolean(
        string='[Non-Official] Show Company VAT', default=True,
    )
    non_official_show_customer_vat = fields.Boolean(
        string='[Non-Official] Show Customer VAT', default=True,
    )
    non_official_show_customer_email = fields.Boolean(
        string='[Non-Official] Show Customer Email', default=False,
    )
    non_official_show_customer_phone = fields.Boolean(
        string='[Non-Official] Show Customer Phone', default=False,
    )
    non_official_show_footer = fields.Boolean(
        string='[Non-Official] Show Footer', default=True,
    )
