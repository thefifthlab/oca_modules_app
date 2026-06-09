# Copyright © 2026 Khichdi InfoTech (https://khichdiinfotech.com)
from odoo import api, models


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        move_type = self.env.context.get("default_move_type")
        if move_type not in ("out_invoice", "in_invoice", "out_refund", "in_refund"):
            return values
        company = self.env.company.root_id
        if not company.currency_sync_auto_on_invoice_open:
            return values
        if self.env.context.get("skip_currency_auto_sync"):
            return values
        self.env["currency.rate.service"].with_context(skip_currency_auto_sync=True).sync_today(
            companies=company,
            source="invoice_open",
            skip_weekend=False,
        )
        return values

