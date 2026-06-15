NV Dual Bookkeeping
===================

Implements a dual-bookkeeping system for Lebanese companies by adding an
**Official (O) / Non-Official (NO)** flag to every financial transaction.

Each journal maintains two independent sequence streams. The Official sequence
master always lives in the designated Official Company — operating company
journals borrow from it, ensuring gap-free, conflict-free numbering across all
companies.

When an Official transaction is posted, the sync engine automatically mirrors
it to the Official Books company. Sync failures are non-blocking: the original
posting is never rolled back.

See ``README.md`` in the module directory for full configuration and
troubleshooting instructions.
