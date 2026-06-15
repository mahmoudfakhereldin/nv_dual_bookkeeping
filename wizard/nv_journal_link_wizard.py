import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class NvJournalLinkWizard(models.TransientModel):
    """
    Wizard to link main-company journals with their counterparts in the
    official company.  Supports auto-matching by journal code or name,
    and allows manual override via an editable list.
    """

    _name = 'nv.journal.link.wizard'
    _description = 'Journal Linking Wizard'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Main Company',
        required=True,
        default=lambda self: self.env.company,
    )

    official_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Official Company',
        compute='_compute_official_company_id',
        store=False,
    )

    line_ids = fields.One2many(
        comodel_name='nv.journal.link.wizard.line',
        inverse_name='wizard_id',
        string='Journal Mappings',
    )

    # -------------------------------------------------------------------------
    # Computed fields
    # -------------------------------------------------------------------------

    @api.depends('company_id')
    def _compute_official_company_id(self):
        for wizard in self:
            wizard.official_company_id = wizard.company_id.official_company_id

    # -------------------------------------------------------------------------
    # default_get — pre-populate lines from main company journals
    # -------------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company

        if not company.official_company_id:
            raise UserError(_(
                "No Official Company is configured for '%s'.\n\n"
                "Please set it in Settings > Accounting > Dual Bookkeeping "
                "before using the Journal Linking Wizard."
            ) % company.name)

        journals = self.env['account.journal'].sudo().search([
            ('company_id', '=', company.id),
        ])

        line_vals = []
        for journal in journals:
            line_vals.append((0, 0, {
                'journal_id': journal.id,
                'official_journal_id': journal.official_journal_id.id or False,
            }))

        res['line_ids'] = line_vals
        res['company_id'] = company.id
        return res

    # -------------------------------------------------------------------------
    # Auto-match methods
    # -------------------------------------------------------------------------

    def action_auto_match_by_code(self):
        """
        For each unmatched line, find a journal in the official company whose
        code exactly matches the main-company journal code and auto-assign it.
        """
        self.ensure_one()
        official_co = self.official_company_id
        if not official_co:
            raise UserError(_("Official Company is not configured. Cannot auto-match."))

        official_journals = self.env['account.journal'].sudo().search([
            ('company_id', '=', official_co.id),
        ])
        official_by_code = {j.code: j for j in official_journals}

        matched = 0
        for line in self.line_ids:
            code = line.journal_id.code
            if code in official_by_code:
                line.official_journal_id = official_by_code[code]
                matched += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Auto-Match by Code'),
                'message': _('%d journal(s) matched by code.') % matched,
                'type': 'info',
                'sticky': False,
            },
        }

    def action_auto_match_by_name(self):
        """
        For each unmatched line, find a journal in the official company whose
        name contains the main-company journal name (case-insensitive).
        """
        self.ensure_one()
        official_co = self.official_company_id
        if not official_co:
            raise UserError(_("Official Company is not configured. Cannot auto-match."))

        official_journals = self.env['account.journal'].sudo().search([
            ('company_id', '=', official_co.id),
        ])

        matched = 0
        for line in self.line_ids:
            if line.official_journal_id:
                continue  # Already mapped — skip
            source_name = (line.journal_id.name or '').lower()
            for oj in official_journals:
                if source_name and source_name in (oj.name or '').lower():
                    line.official_journal_id = oj
                    matched += 1
                    break

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Auto-Match by Name'),
                'message': _('%d journal(s) matched by name.') % matched,
                'type': 'info',
                'sticky': False,
            },
        }

    # -------------------------------------------------------------------------
    # Confirm — persist mappings to account.journal records
    # -------------------------------------------------------------------------

    def action_confirm(self):
        """
        Write the selected official_journal_id onto each main-company journal
        and return a notification summarising the result.
        """
        self.ensure_one()
        linked = 0
        unmatched = 0

        for line in self.line_ids:
            if line.official_journal_id:
                line.journal_id.sudo().write({
                    'official_journal_id': line.official_journal_id.id,
                })
                linked += 1
            else:
                unmatched += 1

        _logger.info(
            "nv_dual_bookkeeping: Journal linking complete — %d linked, %d unmatched "
            "(company: %s → %s).",
            linked, unmatched,
            self.company_id.name, self.official_company_id.name or '?',
        )

        message = _("%(linked)d journal(s) linked successfully. %(unmatched)d journal(s) unmatched.") % {
            'linked': linked,
            'unmatched': unmatched,
        }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Journal Linking Complete'),
                'message': message,
                'type': 'success' if unmatched == 0 else 'warning',
                'sticky': unmatched > 0,
            },
        }


class NvJournalLinkWizardLine(models.TransientModel):
    """
    One line per main-company journal in the Journal Linking Wizard.
    """

    _name = 'nv.journal.link.wizard.line'
    _description = 'Journal Linking Wizard Line'

    wizard_id = fields.Many2one(
        comodel_name='nv.journal.link.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Main Journal',
        required=True,
    )

    journal_code = fields.Char(
        string='Code',
        related='journal_id.code',
        readonly=True,
    )

    official_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Official Journal',
        domain="[('company_id', '=', parent.official_company_id)]",
    )

    match_status = fields.Char(
        string='Status',
        compute='_compute_match_status',
        store=False,
    )

    # -------------------------------------------------------------------------
    # Computed
    # -------------------------------------------------------------------------

    @api.depends('official_journal_id', 'journal_id', 'wizard_id.official_company_id')
    def _compute_match_status(self):
        for line in self:
            if line.official_journal_id:
                line.match_status = _('Matched')
            else:
                # Check whether a code-based match exists without setting it
                official_co = line.wizard_id.official_company_id
                if official_co:
                    code_match = self.env['account.journal'].sudo().search([
                        ('company_id', '=', official_co.id),
                        ('code', '=', line.journal_id.code),
                    ], limit=1)
                    line.match_status = _('Code Match Available') if code_match else _('Unmatched')
                else:
                    line.match_status = _('Unmatched')
