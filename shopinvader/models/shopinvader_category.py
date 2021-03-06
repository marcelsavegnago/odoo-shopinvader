# Copyright 2017 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from collections import defaultdict

from odoo import api, fields, models
from odoo.addons.base_url.models.abstract_url import get_model_ref

from .tools import _build_slugified_field_by_id


class ShopinvaderCategory(models.Model):
    _name = "shopinvader.category"
    _description = "Shopinvader Category"
    _inherit = ["shopinvader.binding", "abstract.url", "seo.title.mixin"]
    _inherits = {"product.category": "record_id"}
    _order = "sequence"

    record_id = fields.Many2one(
        "product.category", required=True, ondelete="cascade", index=True
    )
    object_id = fields.Integer(
        compute="_compute_object_id", store=True, index=True
    )
    sequence = fields.Integer()
    meta_description = fields.Char()
    meta_keywords = fields.Char()
    subtitle = fields.Char()
    short_description = fields.Html()
    description = fields.Html()
    shopinvader_parent_id = fields.Many2one(
        "shopinvader.category",
        "Shopinvader Parent",
        compute="_compute_parent_category",
        store=True,
        index=True,
        compute_sudo=True,
    )
    shopinvader_child_ids = fields.Many2many(
        "shopinvader.category",
        "Shopinvader Childs",
        compute="_compute_child_category",
    )
    level = fields.Integer(compute="_compute_level")
    redirect_url_key = fields.Serialized(
        compute="_compute_redirect_url_key", string="Redirect Url Keys"
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "record_uniq",
            "unique(backend_id, record_id, lang_id)",
            "A category can only have one binding by backend.",
        )
    ]

    @api.multi
    def name_get(self):
        return [(cat.id, cat.record_id.display_name) for cat in self]

    def _compute_redirect_url_key(self):
        for record in self:
            res = []
            for url in record.redirect_url_url_ids:
                res.append(url.url_key)
            record.redirect_url_key = res

    @api.depends("record_id")
    def _compute_object_id(self):
        for record in self:
            record.object_id = record.record_id.id

    @api.depends("parent_id.shopinvader_bind_ids")
    def _compute_parent_category(self):
        for record in self:
            for binding in record.parent_id.shopinvader_bind_ids:
                if (
                    binding.backend_id == record.backend_id
                    and binding.lang_id == record.lang_id
                ):
                    record.shopinvader_parent_id = binding
                    break

    def _compute_child_category(self):
        for record in self:
            record.shopinvader_child_ids = self.search(
                [
                    ("lang_id", "=", record.lang_id.id),
                    ("record_id.parent_id", "=", record.record_id.id),
                    ("backend_id", "=", record.backend_id.id),
                ]
            )

    @api.multi
    @api.depends(
        "lang_id", "record_id.name", "shopinvader_parent_id.automatic_url_key"
    )
    def _compute_automatic_url_key(self):
        records_by_lang = defaultdict(self.browse)
        for record in self:
            records_by_lang[record.lang_id] |= record
        key_by_id = {}
        for lang_id, records in records_by_lang.items():
            key_by_id.update(
                _build_slugified_field_by_id(
                    records.with_context(lang=lang_id.code), "name"
                )
            )
        for record in self:
            key = key_by_id[record.id]
            if record.parent_id and record.shopinvader_parent_id:
                parent_url = record.shopinvader_parent_id.automatic_url_key
                key = "/".join([parent_url, key])
            record.automatic_url_key = key

    @api.depends(
        "shopinvader_parent_id",
        "shopinvader_parent_id.level",
        "shopinvader_parent_id.active",
    )
    def _compute_level(self):
        for record in self:
            record.level = 0
            parent = record.shopinvader_parent_id
            while parent and parent.active:
                record.level += 1
                parent = parent.shopinvader_parent_id

    def _unbind(self):
        shopinvader_child_cat = self.browse()
        for shopinvader_cat in self:
            categ_id = shopinvader_cat.record_id
            childs_cat = self.env["product.category"].search(
                [("id", "child_of", categ_id.id)]
            )
            shopinvader_child_cat = self.search(
                [
                    ("record_id", "in", childs_cat.ids),
                    ("backend_id", "=", shopinvader_cat.backend_id.id),
                ]
            )
        categories = self | shopinvader_child_cat
        categories.write({"active": False})

    def _redirect_existing_url(self):
        for record in self.filtered(lambda c: c.url_url_ids):
            categ = record.shopinvader_parent_id
            if categ:
                record.url_url_ids.write(
                    {"redirect": True, "model_id": get_model_ref(categ)}
                )
        return True
