import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class AccountPartialReconcile(models.Model):
    """
    Hook into reconcile / unreconcile events so that Official payment–invoice
    matches in the main company are automatically mirrored in the official
    company.

    Infinite-loop prevention: the sync engine guards against mirroring
    reconciliations that already involve mirror moves (is_mirror=True), so
    the reconcile/unreconcile created in the official company does not
    trigger another round of mirroring.
    """
    _inherit = 'account.partial.reconcile'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            self.env['nv.sync.engine'].sync_reconcile(rec)
        return records

    def unlink(self):
        # Capture the data we need before the records are deleted.
        reconciles_to_unsync = self.filtered(
            lambda r: r.debit_move_id.move_id.is_official
            and r.credit_move_id.move_id.is_official
            and not r.debit_move_id.move_id.is_mirror
            and not r.credit_move_id.move_id.is_mirror
        )
        # Unsync each one while the record still exists (needs move data).
        for rec in reconciles_to_unsync:
            self.env['nv.sync.engine'].sync_unreconcile(rec)
        return super().unlink()
