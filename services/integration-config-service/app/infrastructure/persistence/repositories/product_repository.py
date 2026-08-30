from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.infrastructure.persistence.models.product import Product


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_many(self, products: Iterable[dict], deactivate_missing: bool = False) -> int:
        items = list(products)
        incoming_codes = [str(item["code"]) for item in items if item.get("code")]

        if deactivate_missing and incoming_codes:
            self.db.query(Product).filter(Product.code.notin_(incoming_codes)).delete(
                synchronize_session=False
            )

        synced = 0
        for product in items:
            code = str(product["code"])
            model = self.db.query(Product).filter(Product.code == code).one_or_none()
            if model is None:
                model = Product(code=code)
                self.db.add(model)

            model.type = product["type"]
            model.description = product["description"]
            model.active = product.get("active", True)
            model.raw_payload = product.get("raw_payload", {})
            synced += 1

        self.db.commit()
        return synced

    def list(self, active: Optional[bool] = None) -> list[Product]:
        query = self.db.query(Product)
        if active is not None:
            query = query.filter(Product.active.is_(active))
        return query.order_by(Product.code.asc()).all()
