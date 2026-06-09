import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    is_official = fields.Boolean(
        string='Official',
        default=lambda self: self._default_is_official(),
        tracking=True,
        copy=False,
        help="When True this transaction consumes the Official (O) sequence. "
             "When False it consumes the Non-Official (NO) sequence. Locked after posting.",
    )

    is_official_set = fields.Boolean(
        string='Official Flag Explicitly Set',
        default=True,
        copy=False,
        help="Tracks whether the user explicitly chose Official or Non-Official "
             "before posting. Used when require_official_flag setting is enabled.",
    )

    dual_sequence_label = fields.Char(
        string='Sequence Type',
        compute='_compute_dual_sequence_label',
        store=False,
    )

    is_mirror = fields.Boolean(
        string='Mirror Entry',
        default=False,
        readonly=True,
        copy=False,
        help="Set to True by the sync engine when this record is a mirror created "
             "in the official company. Mirror entries should not be re-synced.",
    )

    source_move_ref = fields.Char(
        string='Source Reference',
        readonly=True,
        copy=False,
        help="Stores the sequence number of the original transaction in the main company "
             "(e.g. 'BLOM-O/2026/0001'). Set on mirror entries by the sync engine.",
    )

    sync_log_ids = fields.One2many(
        comodel_name='nv.sync.log',
        inverse_name='source_move_id',
        string='Sync Logs',
        copy=False,
    )

    sync_state = fields.Char(
        string='Sync State',
        compute='_compute_sync_state',
        store=False,
        help="Latest sync state derived from sync_log_ids.",
    )

    company_is_official_company = fields.Boolean(
        string='Company Is Official',
        related='company_id.is_official_company',
        store=False,
        help="Passed to views to show the official-company warning banner.",
    )

    company_official_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Official Company',
        related='company_id.official_company_id',
        store=False,
        help="Used in views to show/hide the manual sync button.",
    )

    show_dual_bookkeeping_ui = fields.Boolean(
        string='Show Dual Bookkeeping UI',
        compute='_compute_show_dual_bookkeeping_ui',
        store=False,
        help="True when the current user should see O/NO badges, mirror labels, and sync "
             "status. Always True in operating companies. In the Official Books company, "
             "True only for members of group_view_dual_meta.",
    )

    # -------------------------------------------------------------------------
    # Defaults
    # -------------------------------------------------------------------------

    @api.model
    def _default_is_official(self):
        """
        Official company: always True (all transactions are official there).
        Other companies: read system parameter; default True when absent or 'True'.
        """
        if self.env.company.is_official_company:
            return True
        param = self.env['ir.config_parameter'].sudo().get_param(
            'nv_dual_bookkeeping.default_is_official', 'True'
        )
        return param.strip().lower() not in ('false', '0', '')

    # -------------------------------------------------------------------------
    # Computed fields
    # -------------------------------------------------------------------------

    @api.depends('is_official')
    def _compute_dual_sequence_label(self):
        for move in self:
            move.dual_sequence_label = 'O' if move.is_official else 'NO'

    @api.depends('sync_log_ids', 'sync_log_ids.sync_state', 'sync_log_ids.sync_date')
    def _compute_sync_state(self):
        for move in self:
            logs = move.sync_log_ids.sorted('sync_date', reverse=True)
            move.sync_state = logs[0].sync_state if logs else False

    @api.depends('company_id', 'company_id.is_official_company')
    @api.depends_context('uid')
    def _compute_show_dual_bookkeeping_ui(self):
        """
        Controls whether dual-bookkeeping UI elements (O/NO badge, mirror label,
        sync buttons, source reference) are visible to the current user.

        - Operating company: always visible to all users.
        - Official Books company: visible only to members of group_view_dual_meta.
          This keeps the view clean for external auditors who should see standard
          accounting records without internal classification metadata.
        """
        in_meta_group = self.env.user.has_group('nv_dual_bookkeeping.group_view_dual_meta')
        for move in self:
            if move.company_id.is_official_company:
                move.show_dual_bookkeeping_ui = in_meta_group
            else:
                move.show_dual_bookkeeping_ui = True

    # -------------------------------------------------------------------------
    # Sequence overrides
    # -------------------------------------------------------------------------

    def _get_sequence(self):
        """
        Return the correct ir.sequence for this move based on the is_official flag.

        This is an internal helper called by _set_next_sequence().  It is NOT a
        framework hook — Odoo 18 removed the ir.sequence-based journal entry numbering
        in favour of pattern matching.  We maintain our own ir.sequence records
        (sequence_o_id / sequence_no_id on account.journal) and call next_by_id()
        ourselves in _set_next_sequence().

        Official (O):
          Returns journal_id.sequence_o_master_id, which resolves to:
          - official_journal_id.sequence_o_id  (cross-company shared master), or
          - local journal sequence_o_id         (fallback when no mapping)

        Non-Official (NO):
          Returns journal_id.sequence_no_id (always local).
        """
        self.ensure_one()
        if self.is_official:
            master_seq = self.journal_id.sequence_o_master_id
            if not master_seq:
                raise UserError(_(
                    "Journal '%s' has no Official sequence configured. "
                    "Please map an Official Company Journal in the journal settings."
                ) % self.journal_id.name)
            return master_seq
        else:
            no_seq = self.journal_id.sequence_no_id
            if not no_seq:
                raise UserError(_(
                    "Journal '%s' has no Non-Official sequence configured. "
                    "This sequence should have been created automatically. "
                    "Please reinstall the module or contact your administrator."
                ) % self.journal_id.name)
            return no_seq

    def _set_next_sequence(self):
        """
        Assign the move name by consuming the correct ir.sequence via next_by_id().

        Odoo 18 calls this hook during posting (via sequence.mixin).  We bypass
        the built-in pattern-matching approach and instead call next_by_id() on
        our own ir.sequence records so that:
        - Official entries share a single counter across companies (cross-company master).
        - Non-Official entries use the local per-journal counter.
        - Both produce gap-free, predictable names like BLOM-O/2026/0001.

        Mirror entries are a special case: they represent the SAME transaction as
        their source, so they must carry the identical name — no new sequence number
        is consumed.  source_move_ref holds the source move's name (set by the sync
        engine before creating the mirror).

        Falls back to super() only if neither sequence is configured, ensuring
        non-dual-bookkeeping journals are unaffected.
        """
        self.ensure_one()

        # Mirror entries reuse the source move's name — never consume a new number.
        # This is what keeps the Official sequence gap-free: source + mirror share
        # the same slot (e.g. MISC-O/2026/0001) instead of each taking one.
        if self.is_mirror and self.source_move_ref:
            self.name = self.source_move_ref
            return

        # Only apply custom sequencing when the journal has dual sequences configured
        if not (self.journal_id.sequence_o_id or self.journal_id.sequence_no_id):
            return super()._set_next_sequence()

        try:
            seq = self._get_sequence()
        except UserError:
            raise
        except Exception:
            return super()._set_next_sequence()

        # Pass the move date as context so date-range sequences pick the right period
        seq_date = self.date or fields.Date.today()
        seq_ctx = seq.sudo().with_context(ir_sequence_date=seq_date)

        # Consume the next number, skipping any slot already claimed by a mirror
        # entry.  This handles the edge case where journals were linked AFTER some
        # posting had already occurred with independent sequences: the mirror
        # reused the source name (e.g. INV-O/2026/0001) without incrementing the
        # official-company sequence counter, so the counter is still "behind" the
        # already-occupied name.  We keep consuming until we find a free slot.
        _MAX_ATTEMPTS = 50
        for _attempt in range(_MAX_ATTEMPTS):
            name = seq_ctx.next_by_id()
            taken = self.env['account.move'].sudo().search_count([
                ('name', '=', name),
                ('journal_id', '=', self.journal_id.id),
                ('company_id', '=', self.company_id.id),
                ('id', '!=', self.id),
            ])
            if not taken:
                break
        else:
            raise UserError(_(
                "Could not assign a unique sequence number to '%s' after %d attempts. "
                "Please check the dual-bookkeeping sequence configuration."
            ) % (self.journal_id.name, _MAX_ATTEMPTS))

        self.name = name

    # -------------------------------------------------------------------------
    # Write override — field locking
    # -------------------------------------------------------------------------

    def write(self, vals):
        """
        Enforce rules around is_official:
        1. Cannot be changed once a move is posted.
        2. Cannot be set to False in the Official Books company.
        3. Can only be set to False by users with the appropriate group.
        """
        if 'is_official' in vals:
            for move in self:
                # Rule 1: locked after posting
                if move.state == 'posted':
                    raise UserError(_(
                        "Cannot change the Official/Non-Official status of '%s' "
                        "after it has been posted."
                    ) % move.name)

                # Rule 2: Official Books company — all transactions must stay Official
                if vals['is_official'] is False and move.company_id.is_official_company:
                    raise UserError(_(
                        "All transactions in the Official Books company must be Official. "
                        "The Non-Official flag cannot be used here."
                    ))

            # Mark the flag as explicitly set so require_official_flag validation passes.
            # We do this regardless of the value (True or False) — both are valid explicit choices.
            vals['is_official_set'] = True

            # Rule 3: only privileged users may mark as Non-Official
            if vals['is_official'] is False:
                can_set_no = (
                    self.env.user.has_group('nv_dual_bookkeeping.group_can_set_non_official')
                    or self.env.user.has_group('account.group_account_manager')
                )
                if not can_set_no:
                    raise AccessError(_(
                        "You do not have the rights to mark transactions as Non-Official. "
                        "Please contact your accounting manager."
                    ))

        return super().write(vals)

    # -------------------------------------------------------------------------
    # action_post override
    # -------------------------------------------------------------------------

    def action_post(self):
        """
        Pre-posting validations and post-posting sync trigger.

        1. Require explicit O/NO selection when setting is enabled.
        2. Block direct posting in official company when setting is enabled.
        3. Call super() to perform the actual posting.
        4. Trigger sync engine (non-blocking — never prevents posting).
        """
        ICP = self.env['ir.config_parameter'].sudo()

        for move in self:
            # Validation 1: explicit flag required before posting
            # Skipped for Official Books company — the toggle does not exist there and
            # all transactions are always Official, so no conscious choice is needed.
            require_flag = ICP.get_param(
                'nv_dual_bookkeeping.require_official_flag', 'False'
            ).strip().lower() in ('true', '1')
            if require_flag and not move.is_official_set and not move.company_id.is_official_company:
                raise UserError(_(
                    "Please explicitly set Official or Non-Official on '%s' before posting. "
                    "You can do this using the O/NO toggle on the transaction form."
                ) % (move.name or move.ref or _('this transaction')))

            # Validation 2: block direct posting in official company
            block_direct = ICP.get_param(
                'nv_dual_bookkeeping.block_direct_posting_in_official', 'False'
            ).strip().lower() in ('true', '1')
            if block_direct and move.company_id.is_official_company and not move.is_mirror:
                raise UserError(_(
                    "Direct posting is disabled in the Official Books company. "
                    "Post transactions from the main operating company — "
                    "they will sync to '%s' automatically."
                ) % move.company_id.name)

        # Core posting
        result = super().action_post()

        # Post-posting: trigger sync engine for each eligible move
        for move in self:
            if move.is_official and not move.is_mirror and move.state == 'posted':
                if move.company_id.official_company_id:
                    try:
                        self.env['nv.sync.engine'].sync_move(move)
                    except Exception as e:
                        # Non-blocking: log error but never raise to the user here.
                        # The sync engine itself writes an error log and sends a
                        # bus notification, so the user is informed without losing the post.
                        _logger.error(
                            "nv_dual_bookkeeping: Sync failed for move %s: %s",
                            move.name, str(e),
                        )

        return result

    # -------------------------------------------------------------------------
    # Manual sync action
    # -------------------------------------------------------------------------

    def action_manual_sync(self):
        """
        Manually trigger sync to the official company for a single posted move.
        Restricted to Sync Manager group.
        """
        self.ensure_one()
        if not self.env.user.has_group('nv_dual_bookkeeping.group_sync_manager'):
            raise AccessError(_("Only Dual Bookkeeping Sync Managers can trigger manual sync."))

        if self.state != 'posted':
            raise UserError(_("Only posted transactions can be synced."))
        if not self.is_official:
            raise UserError(_("Only Official transactions are synced to the official company."))
        if self.is_mirror:
            raise UserError(_("Mirror entries cannot be re-synced."))
        if not self.company_id.official_company_id:
            raise UserError(_(
                "No Official Company is configured for '%s'. "
                "Set it in Settings > Accounting > Dual Bookkeeping."
            ) % self.company_id.name)

        self.env['nv.sync.engine'].sync_move(self, triggered_by='manual')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Triggered'),
                'message': _('Synchronisation to the official company has been triggered.'),
                'type': 'success',
                'sticky': False,
            },
        }

    # -------------------------------------------------------------------------
    # Smart button action — open sync logs
    # -------------------------------------------------------------------------

    def action_view_sync_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sync Logs'),
            'res_model': 'nv.sync.log',
            'view_mode': 'list,form',
            'domain': [('source_move_id', '=', self.id)],
            'context': {'default_source_move_id': self.id},
        }
