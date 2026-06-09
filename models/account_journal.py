import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    sequence_no_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Non-Official Sequence',
        readonly=True,
        copy=False,
        help="Auto-created sequence used for Non-Official (NO) transactions in this journal.",
    )

    # In Odoo 18 account.journal no longer carries a sequence_id pointing to ir.sequence
    # (that field was removed in Odoo 16).  We therefore maintain our own ir.sequence
    # for Official transactions — sequence_o_id — exactly as we do for NO.
    sequence_o_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Official Sequence',
        readonly=True,
        copy=False,
        help=(
            "Auto-created sequence used for Official (O) transactions when this "
            "journal has no official_journal_id mapping. Acts as the LOCAL master."
        ),
    )

    official_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Official Company Journal',
        copy=False,
        help=(
            "Mirror journal in the official company. Its sequence_o_id is the MASTER "
            "sequence for all Official (O) transactions posted in this journal from "
            "any company. Leave empty to fall back to this journal's own sequence_o_id."
        ),
    )

    # Exposed as a flat field so view domains can reference it directly without
    # dotted traversal (company_id.official_company_id fails in Odoo 18 domains).
    journal_official_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Official Company (resolved)',
        related='company_id.official_company_id',
        store=False,
    )

    sequence_o_master_id = fields.Many2one(
        comodel_name='ir.sequence',
        string='Official Sequence Master',
        compute='_compute_sequence_o_master',
        store=False,
        help=(
            "The master ir.sequence to consume for Official transactions. "
            "Resolves to the official company journal's sequence_o_id when mapped, "
            "otherwise falls back to this journal's own sequence_o_id."
        ),
    )

    has_dual_sequence = fields.Boolean(
        string='Has Dual Sequence',
        compute='_compute_has_dual_sequence',
        store=False,
        help="True when both Official and Non-Official sequences exist for this journal.",
    )

    # -------------------------------------------------------------------------
    # Computed fields
    # -------------------------------------------------------------------------

    @api.depends('official_journal_id', 'official_journal_id.sequence_o_id', 'sequence_o_id')
    def _compute_sequence_o_master(self):
        """
        Resolve the master Official sequence.

        When official_journal_id is set, the official company journal's sequence_o_id
        is the shared master — all operating companies borrow from it, ensuring a single
        gap-free counter regardless of which company posts first.

        When no official_journal_id is set, fall back to the local sequence_o_id.
        """
        for journal in self:
            if journal.official_journal_id and journal.official_journal_id.sequence_o_id:
                journal.sequence_o_master_id = journal.official_journal_id.sequence_o_id
            else:
                journal.sequence_o_master_id = journal.sequence_o_id

    @api.depends('sequence_no_id', 'sequence_o_id')
    def _compute_has_dual_sequence(self):
        for journal in self:
            journal.has_dual_sequence = bool(journal.sequence_no_id and journal.sequence_o_id)

    # -------------------------------------------------------------------------
    # Sequence creation helpers
    # -------------------------------------------------------------------------

    def _create_no_sequence(self):
        """
        Create a Non-Official ir.sequence for this journal and link it to
        sequence_no_id.  Safe to call multiple times — skips if already set.
        Uses sudo() so it works during post_init_hook regardless of user rights.
        """
        self.ensure_one()
        if self.sequence_no_id:
            return  # Already exists — nothing to do

        code = (self.code or 'JNL').upper()
        seq = self.env['ir.sequence'].sudo().create({
            'name': '%s (Non-Official)' % self.name,
            'code': 'account.journal.no.new',
            'prefix': '%s-NO/%%(year)s/' % code,
            'padding': 4,
            'company_id': self.company_id.id,
            'use_date_range': True,
        })
        # Update code to include the sequence id for global uniqueness
        seq.sudo().write({'code': 'account.journal.no.%d' % seq.id})
        self.sudo().write({'sequence_no_id': seq.id})
        _logger.debug(
            "nv_dual_bookkeeping: Created NO sequence '%s' for journal '%s' (company: %s)",
            seq.name, self.name, self.company_id.name,
        )

    def _create_o_sequence(self):
        """
        Create an Official ir.sequence for this journal and link it to
        sequence_o_id.  Safe to call multiple times — skips if already set.
        """
        self.ensure_one()
        if self.sequence_o_id:
            return  # Already exists — nothing to do

        code = (self.code or 'JNL').upper()
        seq = self.env['ir.sequence'].sudo().create({
            'name': '%s (Official)' % self.name,
            'code': 'account.journal.o.new',
            'prefix': '%s-O/%%(year)s/' % code,
            'padding': 4,
            'company_id': self.company_id.id,
            'use_date_range': True,
        })
        seq.sudo().write({'code': 'account.journal.o.%d' % seq.id})
        self.sudo().write({'sequence_o_id': seq.id})
        _logger.debug(
            "nv_dual_bookkeeping: Created O sequence '%s' for journal '%s' (company: %s)",
            seq.name, self.name, self.company_id.name,
        )

    def _create_dual_sequences(self):
        """Convenience: create both O and NO sequences in one call."""
        self._create_o_sequence()
        self._create_no_sequence()

    def _update_sequences(self):
        """
        Synchronise both sequence names and prefixes whenever the journal
        code or name changes.  Creates missing sequences if needed.
        """
        self.ensure_one()
        code = (self.code or 'JNL').upper()

        if self.sequence_no_id:
            self.sequence_no_id.sudo().write({
                'name': '%s (Non-Official)' % self.name,
                'prefix': '%s-NO/%%(year)s/' % code,
            })
        else:
            self._create_no_sequence()

        if self.sequence_o_id:
            self.sequence_o_id.sudo().write({
                'name': '%s (Official)' % self.name,
                'prefix': '%s-O/%%(year)s/' % code,
            })
        else:
            self._create_o_sequence()

    # -------------------------------------------------------------------------
    # Stat button actions
    # -------------------------------------------------------------------------

    def action_open_no_sequence(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Non-Official Sequence',
            'res_model': 'ir.sequence',
            'res_id': self.sequence_no_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_o_sequence(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Official Sequence',
            'res_model': 'ir.sequence',
            'res_id': self.sequence_o_master_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # -------------------------------------------------------------------------
    # ORM overrides
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        journals = super().create(vals_list)
        for journal in journals:
            journal._create_dual_sequences()
        return journals

    def write(self, vals):
        result = super().write(vals)
        # Keep sequence metadata in sync when the journal's identity changes
        if 'code' in vals or 'name' in vals:
            for journal in self:
                journal._update_sequences()
        return result
