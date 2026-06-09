# Copyright © 2026 Khichdi InfoTech (https://khichdiinfotech.com)
from odoo import fields, models
from odoo.exceptions import ValidationError


class CurrencyRateBackfillWizard(models.TransientModel):
    _name = "currency.rate.backfill.wizard"
    _description = "Currency Rate Backfill Wizard"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company.root_id,
    )
    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)
    currency_ids = fields.Many2many(
        "res.currency",
        string="Currencies",
        help="Leave empty to use configured company currencies.",
    )

    def action_backfill_rates(self):
        self.ensure_one()
        if self.end_date < self.start_date:
            raise ValidationError("End date must be greater than or equal to start date.")
        service = self.env["currency.rate.service"]
        result = service.backfill_rates(
            company=self.company_id,
            start_date=self.start_date,
            end_date=self.end_date,
            currencies=self.currency_ids,
        )
        message = (
            f"Created: {result['created']}, Updated: {result['updated']}, "
            f"Weekends Skipped: {result['skipped_weekends']}, "
            f"Fallback Used: {result['fallback_count']}, "
            f"Failures: {len(result['failed_currencies'])}"
        )
        self.company_id.sudo().write(
            {
                "currency_last_sync_status": message,
                "currency_last_sync_date": fields.Datetime.now(),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Currency Rates",
            "res_model": "res.currency.rate",
            "view_mode": "list,form",
            "domain": [
                ("name", ">=", fields.Date.to_string(self.start_date)),
                ("name", "<=", fields.Date.to_string(self.end_date)),
                ("company_id", "=", self.company_id.id),
            ],
            "context": {"search_default_group_by_currency": 1},
        }

