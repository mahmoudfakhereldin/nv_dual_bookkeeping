import logging

from . import models
from . import services
from . import wizard

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Post-installation hook: ensure every existing journal across every company
    has a Non-Official (NO) ir.sequence record.

    Called once by Odoo after the module tables are created and data files are
    loaded.  Safe to re-run — _create_no_sequence() is idempotent.

    Summary logged at INFO level so administrators can verify the migration
    in the server log without enabling debug mode.
    """
    _logger.info("nv_dual_bookkeeping post_init_hook: starting journal migration …")

    journals = env['account.journal'].sudo().search([], order='company_id, id')

    total = len(journals)
    created = 0
    skipped = 0
    warnings = 0
    errors = 0

    # Group by company for a cleaner log output
    current_company = None

    for journal in journals:
        if journal.company_id != current_company:
            current_company = journal.company_id
            _logger.info(
                "nv_dual_bookkeeping post_init_hook: processing company '%s' …",
                current_company.name,
            )

        # --- O and NO sequence creation (idempotent) ---
        try:
            has_o = bool(journal.sequence_o_id)
            has_no = bool(journal.sequence_no_id)
            if not has_o or not has_no:
                journal._create_dual_sequences()
                created += 1
                _logger.debug(
                    "  [CREATED] sequences for journal '%s' (id=%d, company: %s) "
                    "— O: %s, NO: %s",
                    journal.name, journal.id, journal.company_id.name,
                    'new' if not has_o else 'existing',
                    'new' if not has_no else 'existing',
                )
            else:
                skipped += 1
                _logger.debug(
                    "  [SKIPPED] Journal '%s' already has both sequences",
                    journal.name,
                )
        except Exception as exc:
            errors += 1
            _logger.error(
                "  [ERROR] Could not create NO sequence for journal '%s' (id=%d, company: %s): %s",
                journal.name, journal.id, journal.company_id.name, str(exc),
            )
            # Continue to next journal — one failure must not abort the whole hook

        # --- Official journal mapping warning ---
        if not journal.official_journal_id:
            warnings += 1
            _logger.warning(
                "  [UNLINKED] Journal '%s' (id=%d, company: %s) has no official_journal_id. "
                "Use Accounting > Dual Bookkeeping > Link Official Journals to configure.",
                journal.name, journal.id, journal.company_id.name,
            )

    # --- Summary ---
    _logger.info(
        "nv_dual_bookkeeping post_init_hook complete. "
        "Total journals: %d | NO sequences created: %d | already present: %d | "
        "errors: %d | journals with no official mapping: %d",
        total, created, skipped, errors, warnings,
    )

    if warnings:
        _logger.warning(
            "nv_dual_bookkeeping: %d journal(s) are not linked to an official company journal. "
            "Official transactions in these journals will use the local sequence as a fallback "
            "until you complete the mapping.",
            warnings,
        )

    if errors:
        _logger.error(
            "nv_dual_bookkeeping: %d journal(s) failed during NO sequence creation. "
            "Check the errors above and create the sequences manually or "
            "reinstall the module after fixing the root cause.",
            errors,
        )
