import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    """
    Extend the standard Pay wizard so that:
    - is_official defaults from the source invoice / vendor bill.
    - The user can override it before confirming (subject to group checks).
    - The flag is injected into every payment created by the wizard.
    - In the Official Books company the flag is always True and the toggle
      is hidden (mirroring the account.move / account.payment behaviour).
    """
    _inherit = 'account.payment.register'

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    is_official = fields.Boolean(
        string='Official',
        default=True,
        help="When True the resulting journal entry will use the Official (O) sequence. "
             "Defaults from the source invoice / vendor bill.",
    )

    is_official_set = fields.Boolean(
        string='Official Flag Explicitly Set',
        default=False,
    )

    company_is_official_company = fields.Boolean(
        string='Company Is Official',
        related='company_id.is_official_company',
        store=False,
    )

    # -------------------------------------------------------------------------
    # Default — inherit flag from source invoices
    # -------------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)

        # Force True in the Official Books company — no choice needed there.
        if self.env.company.is_official_company:
            defaults['is_official'] = True
            defaults['is_official_set'] = True
            return defaults

        # Resolve source invoices from line_ids already populated by the parent
        # default_get (handles both active_model=account.move and account.move.line).
        # This is more reliable than reading active_ids directly because Odoo 19
        # sets active_ids to move LINE ids when the wizard is opened from
        # Journal Items, making a direct account.move browse return empty.
        source_moves = self.env['account.move']
        line_ids_cmd = defaults.get('line_ids')
        if line_ids_cmd and isinstance(line_ids_cmd, list) and line_ids_cmd:
            cmd = line_ids_cmd[0]
            if isinstance(cmd, (list, tuple)) and len(cmd) >= 3 and cmd[0] == 6 and cmd[2]:
                source_moves = self.env['account.move.line'].browse(cmd[2]).move_id

        # Fallback: active_ids when active_model is explicitly account.move
        if not source_moves and self._context.get('active_model') == 'account.move':
            source_moves = self.env['account.move'].browse(
                self._context.get('active_ids', [])
            ).exists()

        if source_moves:
            official_vals = set(source_moves.mapped('is_official'))
            # If all source documents agree, inherit that value.
            # If mixed (edge case: paying official + non-official together),
            # default to True (safer) and leave is_official_set=False so
            # the require_official_flag check will ask the user to confirm.
            if len(official_vals) == 1:
                defaults['is_official'] = next(iter(official_vals))
                defaults['is_official_set'] = True  # inherited = explicit
            else:
                defaults['is_official'] = True
                defaults['is_official_set'] = False

        return defaults

    # -------------------------------------------------------------------------
    # Push flag into payment vals
    # -------------------------------------------------------------------------

    def _create_payment_vals_from_wizard(self, batch_result):
        """
        Inject is_official and is_official_set into every payment created by
        this wizard invocation.  account.payment.action_post() then forwards
        both flags to the underlying account.move before posting, which routes
        the move to the correct sequence stream (O or NO).
        """
        vals = super()._create_payment_vals_from_wizard(batch_result)
        vals['is_official'] = self.is_official
        # Always mark as explicitly set: the user either inherited the value
        # from the invoice (consciously accepted it) or changed it manually.
        vals['is_official_set'] = True
        return vals

    # def action_create_payments(self):

    def _init_payments(self, to_process, edit_mode=False):
        """
        Safety net: after payments are created (regardless of which
        _create_payment_vals_from_wizard ran), ensure is_official and
        is_official_set are written to each payment.

        This is necessary because nv_double_currencies overrides
        _create_payment_vals_from_wizard and, when
        enable_second_currency_for_company=True, does NOT call super() —
        our injection above is therefore bypassed.  Writing the flag here
        guarantees it lands on every payment before _post_payments() is called.
        """
        payments = super()._init_payments(to_process, edit_mode=edit_mode)
        if not self.env.company.is_official_company:
            for payment in payments:
                if payment.is_official != self.is_official or not payment.is_official_set:
                    payment.sudo().write({
                        'is_official': self.is_official,
                        'is_official_set': True,
                    })
        return payments
