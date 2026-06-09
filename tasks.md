# nv_dual_bookkeeping — Build Tasks

## Status Legend
- `[ ]` pending
- `[~]` in progress
- `[x]` done
- `[-]` skipped

---

## Phase 0 — Scaffold

- [x] 0.1 Create `__init__.py` (root) — bare file, imports models + services + wizard; also defines `post_init_hook` stub
- [x] 0.2 Create `__manifest__.py` — full manifest with name, version `18.0.1.0.0`,
       dependencies `['account']`, author NV, license LGPL-3, `post_init_hook`,
       and complete `data` + `views` + `security` file lists (all files from final structure)
- [x] 0.3 Create `models/__init__.py` — import all five model files
- [x] 0.4 Create `services/__init__.py` — import sync_engine
- [x] 0.5 Create `wizard/__init__.py` — import nv_journal_link_wizard

---

## Phase 1 — Security (must exist before models reference groups)

- [x] 1.1 `security/nv_dual_bookkeeping_security.xml`
       - Group `group_can_set_non_official`: "Can Mark Transactions as Non-Official",
         inherits `account.group_account_user`
       - Group `group_sync_manager`: "Dual Bookkeeping Sync Manager",
         inherits `account.group_account_manager`

- [x] 1.2 `security/ir.model.access.csv`
       - `nv.sync.log`: account user → read only; account manager → full CRUD
       - `nv.journal.link.wizard`: account manager → full CRUD
       - `nv.journal.link.wizard.line`: account manager → full CRUD

---

## Phase 2 — Models

### 2.1 `models/res_company.py`
- [x] 2.1.1 Add field `official_company_id`: Many2one `res.company`,
         string="Official Company", domain="[('id','!=',id)]", copy=False,
         help text as specified
- [x] 2.1.2 Add computed stored Boolean `is_official_company`:
         `_compute_is_official_company` — True if any other company points to self
         as their `official_company_id`; use `@api.depends` on all companies' field

### 2.2 `models/nv_sync_log.py`
- [x] 2.2.1 Define model `nv.sync.log` with all fields:
         `source_move_id`, `target_move_id`, `source_company_id`, `target_company_id`,
         `sync_date` (Datetime, readonly, default=now), `sync_state` (Selection:
         synced/error/pending), `error_message` (Text), `triggered_by`
         (Selection: auto/manual)
- [x] 2.2.2 Add `action_retry()` method — calls `nv.sync.engine`.sync_move on
         `source_move_id`, guards for group_sync_manager
- [x] 2.2.3 Add `action_retry_all_failed()` model method — loops all error records,
         calls retry for each

### 2.3 `models/account_journal.py`
- [x] 2.3.1 Add field `sequence_no_id`: Many2one `ir.sequence`,
         string="Non-Official Sequence", readonly=True, copy=False
- [x] 2.3.2 Add field `official_journal_id`: Many2one `account.journal`,
         string="Official Company Journal", copy=False, with help text
- [x] 2.3.3 Add computed (store=False) `sequence_o_master_id`:
         returns `official_journal_id.sequence_id` if set, else local `sequence_id`
- [x] 2.3.4 Add computed (store=False) Boolean `has_dual_sequence`:
         True when `sequence_no_id` is set
- [x] 2.3.5 Write helper `_create_no_sequence(journal)` — creates ir.sequence with:
         name "{journal.name} (Non-Official)", code set after creation,
         prefix "{CODE}-NO/%(year)s/", padding=4, company_id, use_date_range=True
- [x] 2.3.6 Override `create()` — after super(), call `_create_no_sequence` for new journal,
         use `@api.model_create_multi`
- [x] 2.3.7 Override `write()` — if `code` or `name` in vals:
         update existing NO sequence prefix and name; if no `sequence_no_id` yet, create it

### 2.4 `models/account_move.py`
- [x] 2.4.1 Add `_default_is_official()` — reads ir.config_parameter
         `nv_dual_bookkeeping.default_is_official`, defaults True
- [x] 2.4.2 Add field `is_official`: Boolean, default=`_default_is_official`,
         tracking=True, copy=False
- [x] 2.4.3 Add field `is_official_set`: Boolean, default=False, copy=False
- [x] 2.4.4 Add computed (store=False) Char `dual_sequence_label`: "O" or "NO"
- [x] 2.4.5 Add field `is_mirror`: Boolean, default=False, readonly=True, copy=False
- [x] 2.4.6 Add field `source_move_ref`: Char, readonly=True, copy=False
- [x] 2.4.7 Add One2many `sync_log_ids` → `nv.sync.log`, inverse_name='source_move_id'
- [x] 2.4.8 Add computed (store=False) Char `sync_state`:
         returns state of latest sync log, or False if none
- [x] 2.4.9 Add related Boolean `company_is_official_company`:
         related='company_id.is_official_company', store=False — for view banners
- [x] 2.4.10 Override `_get_sequence()`:
          - is_official=True → return `journal_id.sequence_o_master_id`
            (raise UserError if missing)
          - is_official=False → return `journal_id.sequence_no_id`
            (raise UserError if missing)
- [x] 2.4.11 Override `_set_next_sequence()` — ensure generated name uses
          correct prefix: `{CODE}-O/{YEAR}/` or `{CODE}-NO/{YEAR}/`
- [x] 2.4.12 Override `write()`:
          - Block `is_official` change on posted records (UserError)
          - Block setting `is_official=False` without `group_can_set_non_official`
            or `account.group_account_manager`
- [x] 2.4.13 Override `action_post()`:
          - If `require_official_flag` param is True and `is_official_set` is False:
            raise UserError asking user to set O/NO
          - If `block_direct_posting_in_official` param is True and
            `company_id.is_official_company=True` and `is_mirror=False`:
            raise UserError blocking direct posting
          - Call super()
          - After super(): trigger sync engine (non-blocking try/except)
- [x] 2.4.14 Add `action_manual_sync()` — guards group_sync_manager,
          calls `nv.sync.engine`.sync_move(self), refreshes view

### 2.5 `models/account_payment.py`
- [x] 2.5.1 Add `is_official`: Boolean, default=True, tracking=True, copy=False
- [x] 2.5.2 Add `is_official_set`: Boolean, default=False, copy=False
- [x] 2.5.3 Override `action_post()` — push `is_official` to linked `move_id`
          before calling super()
- [x] 2.5.4 Override `write()` — same posted-lock logic as account.move

---

## Phase 3 — Sync Engine Service

### 3.1 `services/sync_engine.py`
- [x] 3.1.1 Define AbstractModel `nv.sync.engine`
- [x] 3.1.2 Implement `_get_mirror_account(account, target_company)`:
         search `account.account` in target_company by matching code;
         raise UserError with clear message if not found
- [x] 3.1.3 Implement `_map_partner(partner, target_company)`:
         search by VAT then by name in target_company;
         create minimal partner record if not found
- [x] 3.1.4 Implement `sync_move(source_move)` with all guard clauses:
         - is_official=True, is_mirror=False, state='posted'
         - company_id.official_company_id set
         - no existing 'synced' log for this move
- [x] 3.1.5 Build mirror vals inside `with_company(official_co)` context:
         journal, move_type, date, invoice_date, ref (with [MIRROR:] suffix),
         narration, is_mirror=True, is_official=True, source_move_ref,
         partner_id (mapped), currency_id
- [x] 3.1.6 Mirror all move lines — map each account via `_get_mirror_account`,
         copy debit/credit/name/quantity/price_unit as applicable
- [x] 3.1.7 Create mirror move with `sudo().with_company(official_co)`
- [x] 3.1.8 If `auto_post_mirror` config param True: call `mirror_move.action_post()`
- [x] 3.1.9 Write `nv.sync.log` record with state='synced', sync_date=now,
         source/target companies, triggered_by='auto'
- [x] 3.1.10 Wrap entire method in try/except:
          on exception write nv.sync.log state='error', error_message=str(e),
          log via _logger.error, send non-blocking bus notification warning

---

## Phase 4 — Wizard

### 4.1 `wizard/nv_journal_link_wizard.py`
- [x] 4.1.1 Define `nv.journal.link.wizard` (TransientModel):
         `company_id` (default current), `official_company_id` (computed from
         company_id.official_company_id), `line_ids` One2many
- [x] 4.1.2 Define `nv.journal.link.wizard.line` (TransientModel):
         `wizard_id`, `journal_id`, `official_journal_id`
         (domain filtered to wizard official_company_id),
         computed Char `match_status` ("Matched"/"Unmatched"/"Code Match Available")
- [x] 4.1.3 `action_auto_match_by_code()` — for each line find official journal
         where code == journal_id.code, set official_journal_id
- [x] 4.1.4 `action_auto_match_by_name()` — case-insensitive name contains match
- [x] 4.1.5 `action_confirm()` — write official_journal_id on all mapped journals,
         return notification action with summary "X linked, Y unmatched"
- [x] 4.1.6 `default_get()` override — populate line_ids from current company journals

### 4.2 `wizard/views/nv_journal_link_wizard_views.xml`
- [x] 4.2.1 Form view with header showing "Linking journals from {company} → {official_company}"
- [x] 4.2.2 Tree-editable list: Main Journal Name, Code, → Official Journal dropdown,
         Match Status badge
- [x] 4.2.3 Footer buttons: "Auto-Match by Code", "Auto-Match by Name",
         "Confirm" (primary), "Cancel"
- [x] 4.2.4 ir.actions.act_window for the wizard

---

## Phase 5 — Data

- [x] 5.1 `data/nv_dual_bookkeeping_data.xml`
       - `nv_dual_bookkeeping.default_is_official` = "True"
       - `nv_dual_bookkeeping.require_official_flag` = "False"
       - `nv_dual_bookkeeping.auto_post_mirror` = "False"
       - `nv_dual_bookkeeping.block_direct_posting_in_official` = "False"

---

## Phase 6 — Views

### 6.1 `views/account_journal_views.xml`
- [x] 6.1.1 Inherited journal form — add "Dual Bookkeeping" page/tab with:
         - Field `official_journal_id` (domain filtered to official company)
         - Stat button "NO Sequence" → sequence_no_id.name, links to ir.sequence form
         - Stat button "O Sequence Master" → sequence_o_master_id.name
         - Read-only display of next number for both sequences

### 6.2 `views/account_move_views.xml`
- [x] 6.2.1 Inherited move form — add O/NO toggle below journal field:
         - Official → green badge widget "✓ Official" (invisible when is_mirror)
         - Non-Official → orange badge "⚠ Non-Official" (invisible when is_mirror)
         - Mirror badge "🔗 Mirror Entry" blue (visible only when is_mirror=True)
         - Editable in draft, readonly when posted/cancelled
- [x] 6.2.2 Inherited move form — official company warning banner:
         alert-warning div, invisible when company_is_official_company=False
- [x] 6.2.3 Inherited move form — sync smart button in stat button area:
         "Synced ✓" (green), "Sync Error" (red), "Not Synced" (orange),
         hidden when is_official=False; clicks open nv.sync.log list
- [x] 6.2.4 Inherited move form — "↺ Sync to Official Company" button:
         visible when is_official=True, is_mirror=False, state='posted',
         sync_state != 'synced', company official_company_id set;
         groups=group_sync_manager; calls action_manual_sync()
- [x] 6.2.5 Inherited move list view — add `is_official` visible column
         with colored dot widget (green=Official, orange=Non-Official)
- [x] 6.2.6 Inherited move.line list view — add `is_official` as optional column
         (optional_hide by default)
- [x] 6.2.7 Inherited move search view — add filters:
         "Official", "Non-Official", "Not Synced", "Mirror Entries";
         group-by "Official Status"

### 6.3 `views/account_payment_views.xml`
- [x] 6.3.1 Inherited payment form — same O/NO toggle near journal field,
         locked after posting

### 6.4 `views/res_company_views.xml`
- [x] 6.4.1 Inherited company form — add `official_company_id` field
- [x] 6.4.2 Info banner when `is_official_company=True`:
         "This company is configured as an Official Books mirror company."

### 6.5 `views/nv_sync_log_views.xml`
- [x] 6.5.1 List view with columns: Sync Date, Source Transaction (open_move button),
         Source Company, Mirror Transaction, Target Company, Triggered By,
         State (color widget), Error Message (conditional)
- [x] 6.5.2 Header button "Retry Failed" → calls action_retry_all_failed()
- [x] 6.5.3 Per-row button "Retry" visible when sync_state='error'
- [x] 6.5.4 Search filters: "Errors Only", "Today", "Pending"
- [x] 6.5.5 ir.actions.act_window for sync dashboard

### 6.6 `views/res_config_settings_views.xml`
- [x] 6.6.1 Extend res.config.settings model — add five fields:
         `official_company_id`, `default_is_official`, `require_official_flag`,
         `auto_post_mirror`, `block_direct_posting_in_official`;
         wire config params in `get_values` / `set_values`
- [x] 6.6.2 Inherited settings form — add "Dual Bookkeeping" group under Accounting tab
         with all five fields and their labels/help texts

### 6.7 `views/dual_bookkeeping_menus.xml`
- [x] 6.7.1 Top-level menu group "Dual Bookkeeping" under Accounting app
- [x] 6.7.2 Sub-menu "Official Transactions" → account.move list,
         default domain is_official=True
- [x] 6.7.3 Sub-menu "Non-Official Transactions" → account.move list,
         default domain is_official=False
- [x] 6.7.4 Sub-menu "Sync Dashboard" → nv.sync.log list action
- [x] 6.7.5 Sub-menu "Link Official Journals" → opens nv.journal.link.wizard form
- [x] 6.7.6 Sub-menu "Summary Report" → pivot view on account.move:
         row groupby journal_id, column groupby is_official, measure amount_total

---

## Phase 7 — post_init_hook

- [x] 7.1 Complete `post_init_hook` in root `__init__.py`:
       Loop all journals across all companies (use sudo()):
       - If no sequence_no_id → call _create_no_sequence equivalent
       - Log warning for journals with no official_journal_id mapped

---

## Phase 8 — README

- [x] 8.1 `README.md` — installation checklist, configuration guide (official company,
       journal linking, group assignment), key behaviors, troubleshooting

---

## Implementation Dependency Order

```
Phase 0  (scaffold — __init__, __manifest__, sub-inits)
  → Phase 1  (security XML + access CSV — groups referenced by model fields)
  → Phase 2.1 (res_company — needed by journal + move)
  → Phase 2.2 (nv_sync_log — needed by move One2many)
  → Phase 2.3 (account_journal)
  → Phase 2.4 (account_move — references journal + sync_log)
  → Phase 2.5 (account_payment)
  → Phase 3  (sync_engine — references all move fields)
  → Phase 4  (wizard — references journal + company)
  → Phase 5  (data — config params)
  → Phase 6  (views — all models must exist)
  → Phase 7  (post_init_hook — references journal model logic)
  → Phase 8  (README)
```

---

## Edge Cases — Verification Checklist

| # | Scenario | Task(s) |
|---|----------|---------|
| 1 | Create journal → NO sequence auto-created | 2.3.6 |
| 2 | Post official invoice in main company → master sequence consumed | 2.4.10, 2.4.11 |
| 3 | Post non-official invoice → local NO sequence consumed | 2.4.10, 2.4.11 |
| 4 | Mirror created in official company on post | 3.1.4–3.1.9 |
| 5 | Manual entry in official company advances master sequence | 2.4.10 |
| 6 | Next official invoice in main company has no gap (no conflict) | 2.3.3, 3.1 |
| 7 | Sync fails → posting succeeds, error logged, bus warning shown | 3.1.10, 2.4.13 |
| 8 | Retry sync from dashboard → works | 2.2.2, 6.5.3 |
| 9 | Change is_official after posting → blocked | 2.4.12 |
| 10 | post_init_hook on 50 existing journals → all get NO sequence | 7.1 |
| 11 | Journal with no official_journal_id → clear error on sync | 3.1.4 |
| 12 | Account code missing in official company → clear UserError | 3.1.2 |
| 13 | Mirror move re-synced accidentally → guard clause stops it | 3.1.4 |
| 14 | block_direct_posting_in_official=True → posting blocked in official co | 2.4.13 |
| 15 | Unprivileged user sets is_official=False → blocked | 2.4.12 |
