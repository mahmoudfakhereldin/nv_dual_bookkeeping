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

        active_ids = self._context.get('active_ids', [])
        if active_ids:
            moves = self.env['account.move'].browse(active_ids).exists()
            if moves:
                official_vals = moves.mapped('is_official')
                # If all source documents agree, inherit that value.
                # If mixed (edge case: paying official + non-official together),
                # default to True (safer) and leave is_official_set=False so
                # the require_official_flag check will ask the user to confirm.
                if len(set(official_vals)) == 1:
                    defaults['is_official'] = official_vals[0]
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
        the move to the correct ir.sequence.
        """
        vals = super()._create_payment_vals_from_wizard(batch_result)
        vals['is_official'] = self.is_official
        # Always mark as explicitly set: the user either inherited the value
        # from the invoice (consciously accepted it) or changed it manually.
        vals['is_official_set'] = True
        return vals
