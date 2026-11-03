"""Shared base class for every generated wire model.

The class lives outside ``generated.py`` on purpose: it carries SDK policy
(how unknown fields and aliases are treated), not contract shape.  The
generator emits every model with this base so the policy has exactly one
home and the generated file stays a pure projection of the OpenAPI artifact.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WireModel(BaseModel):
    """Pydantic base for Hub wire models.

    * ``extra="allow"`` keeps additive server fields readable through
      ``model_extra`` instead of failing validation.  Untyped routes (whose
      committed OpenAPI response is a generic object) expose every field this
      way.
    * ``populate_by_name=True`` accepts both the wire alias (``spotId``) and the
      Python name (``spot_id``) when constructing a model locally.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    def __getitem__(self, key: str) -> object:
        """Read a wire field by its wire name, typed or extra."""

        for name, field in type(self).model_fields.items():
            if key == name or key == field.alias:
                return getattr(self, name)
        extra = self.model_extra or {}
        if key in extra:
            return extra[key]
        raise KeyError(key)
