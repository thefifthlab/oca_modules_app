# Copyright © 2026 Khichdi InfoTech (https://khichdiinfotech.com)
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    currency_sync_ids = fields.Many2many(
        related="company_id.currency_sync_ids",
        readonly=False,
    )
    currency_sync_auto_on_invoice_open = fields.Boolean(
        related="company_id.currency_sync_auto_on_invoice_open",
        readonly=False,
    )
    currency_last_sync_status = fields.Text(
        related="company_id.currency_last_sync_status",
        readonly=True,
    )
    currency_last_sync_date = fields.Datetime(
        related="company_id.currency_last_sync_date",
        readonly=True,
    )

    def action_currency_sync_now(self):
        self.ensure_one()
        self.env["currency.rate.service"].sync_today(
            companies=self.company_id.root_id,
            source="manual",
            skip_weekend=False,
        )
        return True

    def action_open_currency_backfill_wizard(self):
        self.ensure_one()
        action = self.env.ref("kh_currency_rate_sync.action_currency_rate_backfill_wizard").read()[0]
        action["context"] = {
            "default_company_id": self.company_id.root_id.id,
        }
        return action

