from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FavoriteResponse(BaseModel):
    product_id: uuid.UUID
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)
