# Copyright © 2026 Khichdi InfoTech (https://khichdiinfotech.com)
{
    "name": "Odoo Currency Rate Update Sync",
    "summary": "Automated daily currency exchange rate sync with ECB & Frankfurter. Backdate historical currency rate pulling, invoice open auto-sync, and multi-company support.",
    "description": """
Odoo Currency Rate Update Sync
==============================
This module provides a robust solution for synchronizing currency exchange rates in Odoo.

Key Features:
-------------
* **Reliable Providers:** Primary synchronization via ECB (European Central Bank) with automatic fallback to Frankfurter.
* **Automated Daily Sync:** Keeps your exchange rates up-to-date automatically.
* **Multi-Company Support:** Independent currency settings for each company.
* **Historical Rate Pulling:** Easily fetch and backfill currency rates for past dates.
* **Invoice Auto-Sync:** Automatically updates the current date's currency rate whenever a new invoice is opened.
    """,
    "version": "18.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Khichdi InfoTech",
    "website": "https://khichdiinfotech.com/",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/res_config_settings_views.xml",
        "wizard/currency_rate_backfill_wizard_views.xml",
    ],
    "images": ["static/description/banner.png", "static/description/icon.png"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
