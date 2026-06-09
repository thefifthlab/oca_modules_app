# Copyright © 2026 Khichdi InfoTech (https://khichdiinfotech.com)
import datetime
import logging
import time
from decimal import Decimal, InvalidOperation, getcontext

import requests
from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

LOCK_KEY = 174221
ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
FRANKFURTER_BASE_URL = "https://api.frankfurter.app"


class CurrencyRateService(models.AbstractModel):
    _name = "currency.rate.service"
    _description = "Currency Rate Synchronization Service"

    @api.model
    def sync_today(self, companies=None, source="manual", skip_weekend=True):
        companies = companies or self.env.company.root_id
        companies = companies.filtered(lambda c: not c.parent_id)
        today = fields.Date.today()
        if skip_weekend and today.weekday() >= 5:
            for company in companies:
                company.sudo().write(
                    {
                        "currency_last_sync_status": f"Skipped on weekend for {today}",
                        "currency_last_sync_date": fields.Datetime.now(),
                    }
                )
            return True

        lock_acquired = False
        if source == "cron":
            self.env.cr.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
            lock_acquired = bool(self.env.cr.fetchone()[0])
            if not lock_acquired:
                _logger.info("[Currency Sync] Cron lock busy, skipping this run.")
                return True

        try:
            ecb_payload = self._fetch_ecb_latest()
            frank_payload = None
            for company in companies:
                company = company.with_company(company)
                payload = ecb_payload
                provider_used = "ecb"
                base_code = company.currency_id.name
                if not payload or base_code not in payload["rates"]:
                    _logger.warning("ECB failed, switching to Frankfurter")
                    frank_payload = frank_payload or self._fetch_frankfurter_latest()
                    payload = frank_payload
                    provider_used = "frankfurter"
                if not payload or base_code not in payload["rates"]:
                    status = f"No provider data available for {today} (base={base_code})"
                    company.sudo().write(
                        {"currency_last_sync_status": status, "currency_last_sync_date": fields.Datetime.now()}
                    )
                    _logger.warning("[Currency Sync] company=%s status=%s", company.name, status)
                    continue

                result = self._upsert_day_rates(
                    company=company,
                    rate_date=payload["date"],
                    rates=payload["rates"],
                    provider=provider_used,
                )
                status = (
                    f"OK provider={provider_used} date={payload['date']} "
                    f"created={result['created']} updated={result['updated']} "
                    f"fallback={result['fallback_count']} failed={len(result['failed_currencies'])}"
                )
                company.sudo().write(
                    {"currency_last_sync_status": status, "currency_last_sync_date": fields.Datetime.now()}
                )
            return True
        finally:
            if lock_acquired:
                self.env.cr.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))

    @api.model
    def backfill_rates(self, company, start_date, end_date, currencies=None):
        if end_date < start_date:
            raise ValidationError("End date must be greater than or equal to start date.")
        if (end_date - start_date).days > 730:
            raise ValidationError("Max 2 years allowed.")

        company = company.root_id.with_company(company.root_id)
        currencies = self._get_target_currencies(company, currencies=currencies)
        if not currencies:
            return {
                "created": 0,
                "updated": 0,
                "skipped_weekends": 0,
                "fallback_count": 0,
                "failed_currencies": [],
            }

        range_payload = self._fetch_frankfurter_range(start_date, end_date)
        if not range_payload:
            raise ValidationError("Unable to fetch Frankfurter historical data.")
        rates_by_date = range_payload.get("rates", {})

        totals = {"created": 0, "updated": 0, "skipped_weekends": 0, "fallback_count": 0, "failed_currencies": []}
        current = start_date
        while current <= end_date:
            if current.weekday() >= 5:
                totals["skipped_weekends"] += 1
                current += datetime.timedelta(days=1)
                continue

            day_key = fields.Date.to_string(current)
            day_rates = dict(rates_by_date.get(day_key, {}))
            day_rates.setdefault("EUR", 1.0)
            if company.currency_id.name not in day_rates:
                totals["failed_currencies"].append(f"{day_key}:{company.currency_id.name}")
                current += datetime.timedelta(days=1)
                continue

            result = self._upsert_day_rates(
                company=company,
                rate_date=current,
                rates=day_rates,
                provider="frankfurter",
                currencies=currencies,
            )
            totals["created"] += result["created"]
            totals["updated"] += result["updated"]
            totals["fallback_count"] += result["fallback_count"]
            totals["failed_currencies"].extend(result["failed_currencies"])
            current += datetime.timedelta(days=1)
            if (current - start_date).days % 120 == 0:
                time.sleep(0.05)
        _logger.warning("[Currency Sync] partial_failure currencies=%s", totals["failed_currencies"])
        return totals

    def _upsert_day_rates(self, company, rate_date, rates, provider, currencies=None):
        CurrencyRate = self.env["res.currency.rate"].sudo()
        rate_date_str = fields.Date.to_string(rate_date)
        currencies = self._get_target_currencies(company, currencies=currencies)
        if not currencies:
            return {"created": 0, "updated": 0, "fallback_count": 0, "failed_currencies": []}

        getcontext().prec = 12
        domain = [
            ("company_id", "=", company.id),
            ("name", "=", rate_date_str),
            ("currency_id", "in", currencies.ids),
        ]
        existing_map = {
            record.currency_id.id: record
            for record in CurrencyRate.search(domain)
        }
        to_create_vals = []
        to_update = []
        created = 0
        updated = 0
        fallback_count = 0
        failed_currencies = []
        base_code = company.currency_id.name
        for currency in currencies:
            currency_code = currency.name
            if currency_code not in rates:
                previous = self._get_previous_rate(company, currency, rate_date_str)
                if previous is None:
                    failed_currencies.append(f"{rate_date_str}:{currency_code}")
                    continue
                rate_value = previous
                fallback_count += 1
            else:
                try:
                    rate_value = self._compute_odoo_rate(
                        rates=rates,
                        currency_code=currency_code,
                        base_code=base_code,
                        decimal_places=currency.decimal_places,
                    )
                except (InvalidOperation, ZeroDivisionError, KeyError):
                    failed_currencies.append(f"{rate_date_str}:{currency_code}")
                    continue

            if rate_value <= 0:
                _logger.warning("Invalid rate detected, skipping %s on %s", currency_code, rate_date_str)
                failed_currencies.append(f"{rate_date_str}:{currency_code}")
                continue

            vals = {
                "currency_id": currency.id,
                "company_id": company.id,
                "name": rate_date_str,
                "rate": rate_value,
            }
            existing = existing_map.get(currency.id)
            if existing:
                to_update.append((existing, vals))
            else:
                to_create_vals.append(vals)

        if to_create_vals:
            CurrencyRate.create(to_create_vals)
            created = len(to_create_vals)
        for record, vals in to_update:
            record.write({"rate": vals["rate"]})
            updated += 1

        _logger.info(
            "[Currency Sync] company=%s provider=%s date=%s created=%s updated=%s fallback=%s",
            company.name,
            provider,
            rate_date_str,
            created,
            updated,
            fallback_count,
        )
        return {
            "created": created,
            "updated": updated,
            "fallback_count": fallback_count,
            "failed_currencies": failed_currencies,
        }

    def _get_target_currencies(self, company, currencies=None):
        currencies = currencies or company.currency_sync_ids
        if not currencies:
            currencies = self.env["res.currency"].search([("active", "=", True)])
        return currencies.filtered(lambda c: c.active and c != company.currency_id)

    def _compute_odoo_rate(self, rates, currency_code, base_code, decimal_places):
        base_rate = Decimal(str(rates[base_code]))
        target_rate = Decimal(str(rates[currency_code]))
        # Match Enterprise currency_rate_live behavior:
        # technical rate stored in res.currency.rate = provider_rate / base_currency_rate.
        odoo_rate = target_rate / base_rate
        return float(round(odoo_rate, decimal_places + 6))

    def _get_previous_rate(self, company, currency, rate_date):
        previous = (
            self.env["res.currency.rate"]
            .sudo()
            .search(
                [
                    ("company_id", "=", company.id),
                    ("currency_id", "=", currency.id),
                    ("name", "<", rate_date),
                ],
                order="name desc",
                limit=1,
            )
        )
        return previous.rate if previous else None

    def _fetch_ecb_latest(self):
        response = self._request(ECB_DAILY_URL)
        if not response:
            return None
        try:
            root = etree.fromstring(response.content)
            ns = {"gesmes": "http://www.gesmes.org/xml/2002-08-01", "def": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
            cube_time = root.xpath(".//def:Cube/def:Cube[@time]", namespaces=ns)
            if not cube_time:
                return None
            date_text = cube_time[0].attrib.get("time")
            rates = {"EUR": 1.0}
            for node in cube_time[0].xpath("./def:Cube[@currency and @rate]", namespaces=ns):
                rates[node.attrib["currency"]] = float(node.attrib["rate"])
            if not rates:
                return None
            return {"date": fields.Date.to_date(date_text), "rates": rates}
        except Exception:
            return None

    def _fetch_frankfurter_latest(self):
        response = self._request(f"{FRANKFURTER_BASE_URL}/latest")
        if not response:
            return None
        try:
            data = response.json()
            if data.get("base") != "EUR":
                _logger.warning("Unexpected base from Frankfurter")
                return None
            rates = dict(data.get("rates", {}))
            rates.setdefault("EUR", 1.0)
            return {"date": fields.Date.to_date(data.get("date")), "rates": rates}
        except Exception:
            return None

    def _fetch_frankfurter_range(self, start_date, end_date):
        response = self._request(
            f"{FRANKFURTER_BASE_URL}/{fields.Date.to_string(start_date)}..{fields.Date.to_string(end_date)}"
        )
        if not response:
            return None
        try:
            data = response.json()
            if data.get("base") != "EUR":
                _logger.warning("Unexpected base from Frankfurter")
                return None
            return data
        except Exception:
            return None

    def _request(self, url):
        for attempt in range(2):
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                return response
            except requests.RequestException:
                if attempt == 1:
                    return None
                time.sleep(1)
        return None

