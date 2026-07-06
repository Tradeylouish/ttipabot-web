import datetime
from dataclasses import dataclass
from typing import Optional

import sqlalchemy as sa
import sqlalchemy.orm as so
from flask import url_for

from app import db
from app.temporal_db import temporal_query


@dataclass
class Movement:
    old_name: str
    old_firm: str
    new_name: str
    new_firm: str
    movement_date: datetime.date

    def to_dict(self):
        return {
            "old_name": self.old_name,
            "old_firm": self.old_firm,
            "new_name": self.new_name,
            "new_firm": self.new_firm,
            "movement_date": self.movement_date.isoformat() if self.movement_date else None,
        }


class PaginatedAPIMixin:
    @staticmethod
    def to_collection_dict(query, page, per_page, endpoint, **kwargs):
        resources = db.paginate(query, page=page, per_page=per_page, error_out=False)
        data = {
            "items": [item.to_dict() for item in resources.items],
            "_meta": {
                "page": page,
                "per_page": per_page,
                "total_pages": resources.pages,
                "total_items": resources.total,
            },
            "_links": {
                "self": url_for(endpoint, page=page, per_page=per_page, **kwargs),
                "next": url_for(endpoint, page=page + 1, per_page=per_page, **kwargs)
                if resources.has_next
                else None,
                "prev": url_for(endpoint, page=page - 1, per_page=per_page, **kwargs)
                if resources.has_prev
                else None,
            },
        }
        return data

    @staticmethod
    def to_collection_dict_from_rows(rows, page, per_page, total, endpoint, **kwargs):
        start = (page - 1) * per_page
        end = start + per_page
        page_items = rows[start:end]
        total_pages = (total + per_page - 1) // per_page
        data = {
            "items": [item.to_dict() for item in page_items],
            "_meta": {
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "total_items": total,
            },
            "_links": {
                "self": url_for(endpoint, page=page, per_page=per_page, **kwargs),
                "next": url_for(endpoint, page=page + 1, per_page=per_page, **kwargs)
                if page < total_pages
                else None,
                "prev": url_for(endpoint, page=page - 1, per_page=per_page, **kwargs)
                if page > 1
                else None,
            },
        }
        return data


class Attorney(db.Model, PaginatedAPIMixin):
    __tablename__ = "attorneys"
    id: so.Mapped[int] = so.mapped_column(
        sa.Integer, primary_key=True, autoincrement=True
    )
    external_id: so.Mapped[str] = so.mapped_column(
        sa.String(36), index=True
    )  # UUID format
    name: so.Mapped[str] = so.mapped_column(sa.String(64), index=True)
    phone: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32))
    email: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120), index=True)
    firm: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128), index=True)
    consolidated_firm_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey("consolidated_firms.id"), index=True
    )
    firm_record: so.Mapped[Optional[ConsolidatedFirm]] = so.relationship(
        back_populates="attorneys"
    )
    address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128))
    additional_information: so.Mapped[Optional[str]] = so.mapped_column(
        sa.String(256)
    )
    patents: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    trademarks: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    valid_from: so.Mapped[sa.Date] = so.mapped_column(sa.Date, index=True)
    valid_to: so.Mapped[Optional[sa.Date]] = so.mapped_column(sa.Date, index=True)

    def previous_firm(self):
        # Query for previous firm record
        query = (
            sa.select(Attorney)
            .where(
                sa.and_(
                    Attorney.external_id == self.external_id,
                    Attorney.valid_from < self.valid_from,
                    Attorney.firm != self.firm,
                )
            )
            .order_by(Attorney.valid_from.desc())
        )
        prev = db.session.execute(query).scalars().first()
        return prev.firm if prev else self.firm

    def to_dict(self):
        return {
            "id": self.external_id,
            "name": self.name,
            "name_length": len(self.name),
            "phone": self.phone,
            "email": self.email,
            "firm": self.firm,
            "address": self.address,
            "additional_information": self.additional_information,
            "patents": self.patents,
            "trademarks": self.trademarks,
        }

    def __repr__(self):
        return f"<Attorney {self.name}>"


class IncorporatedFirm(db.Model, PaginatedAPIMixin):
    __tablename__ = "firms"
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    external_id: so.Mapped[Optional[str]] = so.mapped_column(
        sa.String(36), index=True
    )  # UUID format
    consolidated_firm_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey("consolidated_firms.id"), index=True
    )
    name: so.Mapped[str] = so.mapped_column(sa.String(128), index=True)
    phone: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32))
    email: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120), index=True)
    website: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120), index=True)
    directors: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256), index=True)
    address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128))
    patents: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    trademarks: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)

    consolidated_firm: so.Mapped[Optional[ConsolidatedFirm]] = so.relationship(
        back_populates="incorporated_firms"
    )

    def to_dict(self):
        return {
            "id": self.external_id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "website": self.website,
            "address": self.address,
            "patents": self.patents,
            "trademarks": self.trademarks,
        }

    def __repr__(self):
        return f"<Incorporated Firm {self.name}>"


class ConsolidatedFirm(db.Model, PaginatedAPIMixin):
    __tablename__ = "consolidated_firms"
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    name: so.Mapped[str] = so.mapped_column(sa.String(128), index=True)

    attorneys: so.Mapped[list[Attorney]] = so.relationship(back_populates="firm_record")
    incorporated_firms: so.Mapped[list[IncorporatedFirm]] = so.relationship(
        back_populates="consolidated_firm"
    )

    def to_dict(self):
        return {
            "name": self.name,
        }

    def __repr__(self):
        return f"<Firm {self.name}>"

    def attorney_count(self, as_of_date: datetime.date = None) -> int:
        """Returns the number of attorneys valid as of a given date."""
        if as_of_date is None:
            as_of_date = datetime.date.today()

        query = temporal_query(
            Attorney,
            as_of_date,
            criterion=[Attorney.consolidated_firm_id == self.id],
            columns=[sa.func.count(Attorney.id)],
        )
        return db.session.execute(query).scalar()
