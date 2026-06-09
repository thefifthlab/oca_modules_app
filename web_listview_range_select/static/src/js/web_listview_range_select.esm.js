/** @odoo-module */

import { ListRenderer } from "@web/views/list/list_renderer";
import { patch } from "@web/core/utils/patch";

// Odoo 18: patch() takes 2 args — (prototype, patchObject).
// The 3-arg form (name as second argument) was removed in Odoo 17+.
patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.range_history = [];
    },

    _getRangeSelection() {
        // Get the two boundary checkboxes that were previously clicked
        let start = null;
        let end = null;
        const rows = document.querySelectorAll("tr[data-id] td.o_list_record_selector input");
        rows.forEach((el, i) => {
            const id = el.closest("tr").dataset.id;
            const checked = this.range_history.indexOf(id) !== -1;
            if (checked && el.checked) {
                if (start === null) {
                    start = i;
                } else {
                    end = i;
                }
            }
        });
        return this._getSelectionByRange(start, end);
    },

    _getSelectionByRange(start, end) {
        const result = [];
        document.querySelectorAll("tr[data-id]").forEach((el, i) => {
            const recordId = el.dataset.id;
            if (start !== null && end !== null && i >= start && i <= end) {
                result.push(recordId);
            } else if (start !== null && end === null && start === i) {
                result.push(recordId);
            }
        });
        // Deduplicate
        return [...new Set(result)];
    },

    _pushRangeHistory(id) {
        if (this.range_history.length === 2) {
            this.range_history = [];
        }
        this.range_history.push(id);
    },

    _deselectTable() {
        // Clear any accidental text selection caused by shift-click
        window.getSelection().removeAllRanges();
    },

    _onClickSelectRecord(record, ev) {
        const el = ev.currentTarget;
        const checkbox = el.querySelector("input");
        if (checkbox && checkbox.checked) {
            const tr = el.closest("tr");
            if (tr) {
                this._pushRangeHistory(tr.dataset.id);
            }
        }
        if (ev.shiftKey) {
            const selection = this._getRangeSelection();
            document.querySelectorAll("tr[data-id]").forEach((tr) => {
                const recordId = tr.dataset.id;
                if (selection.includes(recordId)) {
                    const input = tr.querySelector("td.o_list_record_selector input");
                    if (input) {
                        input.checked = true;
                    }
                }
            });
            this._checkBoxSelections(selection);
            this._deselectTable();
        }
    },

    _checkBoxSelections(selection) {
        const records = this.props.list.records;
        for (const rec of records) {
            // Mark every record in range as selected, except the last anchor
            const idx = selection.indexOf(rec.id);
            if (idx !== -1 && idx !== selection.length - 1) {
                rec.toggleSelection(true);
            }
        }
    },
});
