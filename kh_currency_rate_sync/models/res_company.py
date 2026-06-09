# Copyright © 2026 Khichdi InfoTech (https://khichdiinfotech.com)
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    currency_sync_ids = fields.Many2many(
        "res.currency",
        "res_company_currency_sync_rel",
        "company_id",
        "currency_id",
        string="Currencies To Sync",
        help="Currencies that should be updated against the company base currency.",
    )
    currency_sync_auto_on_invoice_open = fields.Boolean(
        string="Auto Sync On Invoice Open",
        default=False,
        help="When enabled, opening a new customer/vendor invoice triggers a rate sync for today.",
    )
    currency_last_sync_status = fields.Text(
        string="Last Currency Sync Status",
        readonly=True,
    )
    currency_last_sync_date = fields.Datetime(
        string="Last Currency Sync Date",
        readonly=True,
    )

    def cron_update_currency_rates(self):
        service = self.env["currency.rate.service"]
        companies = self.search([("parent_id", "=", False)])
        service.sync_today(companies=companies, source="cron", skip_weekend=True)

