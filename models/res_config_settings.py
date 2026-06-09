import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # -------------------------------------------------------------------------
    # Official company — stored on res.company via related
    # -------------------------------------------------------------------------

    official_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Official Mirror Company',
        related='company_id.official_company_id',
        readonly=False,
        help=(
            "All Official transactions posted in the current company will be "
            "automatically mirrored to this company."
        ),
    )

    # -------------------------------------------------------------------------
    # Boolean settings — stored as ir.config_parameter
    # Odoo 18 handles True/False serialisation automatically for Boolean fields
    # with the config_parameter attribute.
    # -------------------------------------------------------------------------

    # NOTE: cannot use 'default_is_official' — Odoo 18 reserves the 'default_'
    # prefix for model-default-value settings and raises if default_model is absent.
    nv_default_is_official = fields.Boolean(
        string='Default new transactions as Official',
        config_parameter='nv_dual_bookkeeping.default_is_official',
        help=(
            "When enabled, all new journal entries, invoices, and payments "
            "will default to Official. Users can override per-transaction."
        ),
    )

    require_official_flag = fields.Boolean(
        string='Require explicit Official/Non-Official selection before posting',
        config_parameter='nv_dual_bookkeeping.require_official_flag',
        help=(
            "When enabled, users must explicitly set the Official or Non-Official "
            "flag before they are allowed to post a transaction."
        ),
    )

    auto_post_mirror = fields.Boolean(
        string='Auto-post mirrored transactions in official company',
        config_parameter='nv_dual_bookkeeping.auto_post_mirror',
        help=(
            "When enabled, mirror entries in the official company are posted "
            "automatically. When disabled (recommended), they remain in draft "
            "for manual review before posting."
        ),
    )

    block_direct_posting_in_official = fields.Boolean(
        string='Block direct manual posting in Official Company',
        config_parameter='nv_dual_bookkeeping.block_direct_posting_in_official',
        help=(
            "When enabled, only mirror entries created by the sync engine can be "
            "posted in the official company. This prevents sequence gaps and "
            "duplicate entries. Recommended for strict dual-bookkeeping setups."
        ),
    )
