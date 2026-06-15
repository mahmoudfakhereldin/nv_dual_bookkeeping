import logging
from datetime import date as _date
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    official_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Official Company Journal',
        copy=False,
        help=(
            "Mirror journal in the official company. Leave empty if this journal "
            "is not used for Official (O) transactions that sync to the official company."
        ),
    )

    # Exposed as a flat field so view domains can reference it directly without
    # dotted traversal (company_id.official_company_id fails in Odoo 19 domains).
    journal_official_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Official Company (resolved)',
        related='company_id.official_company_id',
        store=False,
    )

    seq_prefix_o = fields.Char(
        string='Official Sequence Prefix',
        help=(
            'Prefix code for Official entries (e.g. BANK-O). '
            'Entries will be numbered BANK-O/2026/0001.'
        ),
    )

    seq_prefix_no = fields.Char(
        string='Non-Official Sequence Prefix',
        help=(
            'Prefix code for Non-Official entries (e.g. BANK-NO). '
            'Entries will be numbered BANK-NO/2026/0001.'
        ),
    )

    seq_preview_o = fields.Char(
        string='Next Official Entry',
        compute='_compute_seq_previews',
        store=False,
    )

    seq_preview_no = fields.Char(
        string='Next Non-Official Entry',
        compute='_compute_seq_previews',
        store=False,
    )

    # -------------------------------------------------------------------------
    # Computed fields
    # -------------------------------------------------------------------------

    @api.depends('seq_prefix_o', 'seq_prefix_no')
    def _compute_seq_previews(self):
        year = _date.today().year
        for journal in self:
            for result_field, prefix_val, is_official in [
                ('seq_preview_o', journal.seq_prefix_o, True),
                ('seq_preview_no', journal.seq_prefix_no, False),
            ]:
                if not prefix_val:
                    journal[result_field] = ''
                    continue
                seq_prefix = '%s/%04d/' % (prefix_val, year)
                last_move = self.env['account.move'].sudo().search([
                    ('journal_id', '=', journal.id),
                    ('is_official', '=', is_official),
                    ('sequence_prefix', '=', seq_prefix),
                    ('state', '=', 'posted'),
                ], order='sequence_number desc', limit=1)
                next_num = (last_move.sequence_number + 1) if last_move else 1
                journal[result_field] = '%s%04d' % (seq_prefix, next_num)

    # -------------------------------------------------------------------------
    # Cross-company read helpers
    # -------------------------------------------------------------------------

    def _official_journal_company_ctx(self):
        """Return context dict that adds the official companies to
        allowed_company_ids so cross-company official_journal_id Many2one
        values can be resolved without triggering record-rule access errors."""
        if not self.ids:
            return None
        self.env.cr.execute("""
            SELECT DISTINCT j2.company_id
              FROM account_journal j1
              JOIN account_journal j2 ON j2.id = j1.official_journal_id
             WHERE j1.id IN %s
        """, [tuple(self.ids)])
        official_cos = {r[0] for r in self.env.cr.fetchall()}
        if not official_cos:
            return None
        current = set(self.env.context.get('allowed_company_ids') or [self.env.company.id])
        extra = official_cos - current
        if not extra:
            return None
        return {'allowed_company_ids': list(current | extra)}

    def read(self, fields=None, load='_classic_read'):
        if not self.env.su and (fields is None or 'official_journal_id' in (fields or [])):
            ctx = self._official_journal_company_ctx()
            if ctx:
                return self.with_context(**ctx).read(fields=fields, load=load)
        return super().read(fields=fields, load=load)

    def web_read(self, specification):
        if not self.env.su and 'official_journal_id' in specification:
            ctx = self._official_journal_company_ctx()
            if ctx:
                return self.with_context(**ctx).web_read(specification)
        return super().web_read(specification)

    # -------------------------------------------------------------------------
    # ORM overrides
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        journals = super().create(vals_list)
        for journal in journals:
            # Auto-populate prefixes when not explicitly provided
            updates = {}
            if not journal.seq_prefix_o:
                code = (journal.code or 'JNL').upper()
                updates['seq_prefix_o'] = '%s-O' % code
            if not journal.seq_prefix_no:
                code = (journal.code or 'JNL').upper()
                updates['seq_prefix_no'] = '%s-NO' % code
            if updates:
                journal.sudo().write(updates)
        return journals
