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

    @api.depends('official_company_id')
    def _compute_is_official_company(self):
        """
        A company is considered an 'Official Company' when any other company
        in the system has selected it as their official_company_id.

        We search across all companies (sudo) so the computed field stays
        accurate regardless of the current user's company access.
        """
        all_companies = self.env['res.company'].sudo().search([
            ('official_company_id', '!=', False),
        ])
        # Build a set of company IDs that are targeted as official mirrors
        official_ids = set(all_companies.mapped('official_company_id').ids)

        for company in self:
            company.is_official_company = company.id in official_ids
