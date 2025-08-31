from typing import Optional

import sqlalchemy as sa
import sqlalchemy.orm as so
from flask import url_for

from app import db


class PaginatedAPIMixin(object):
    @staticmethod
    def to_collection_dict(query, page, per_page, endpoint, **kwargs):
        resources = db.paginate(query, page=page, per_page=per_page,
                                error_out=False)
        data = {
            'items': [item.to_dict() for item in resources.items],
            '_meta': {
                'page': page,
                'per_page': per_page,
                'total_pages': resources.pages,
                'total_items': resources.total
            },
            '_links': {
                'self': url_for(endpoint, page=page, per_page=per_page,
                                **kwargs),
                'next': url_for(endpoint, page=page + 1, per_page=per_page,
                                **kwargs) if resources.has_next else None,
                'prev': url_for(endpoint, page=page - 1, per_page=per_page,
                                **kwargs) if resources.has_prev else None
            }
        }
        return data

class Attorney(db.Model, PaginatedAPIMixin):
    __tablename__ = 'attorneys'
    id: so.Mapped[int] = so.mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    external_id: so.Mapped[str] = so.mapped_column(sa.String(36), index=True)  # UUID format
    name: so.Mapped[str] = so.mapped_column(sa.String(64), index=True)
    phone: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32))
    email: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120), index=True)
    firm: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128), index=True)
    firm_id: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey('firms.id'),
                                               index=True)
    firm_record: so.Mapped[Optional["Firm"]] = so.relationship("Firm", back_populates="attorneys")
    address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128))
    patents: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    trademarks: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    valid_from: so.Mapped[sa.Date] = so.mapped_column(sa.Date, index=True)
    valid_to: so.Mapped[Optional[sa.Date]] = so.mapped_column(sa.Date, index=True)

    def name_length(self):
        return len(self.name)

    def previous_firm(self):
        # Query for previous firm record
        query = sa.select(Attorney).where(
            sa.and_(
                Attorney.external_id == self.external_id,
                Attorney.valid_from < self.valid_from,
                Attorney.firm != self.firm
            )
        ).order_by(Attorney.valid_from.desc())
        prev = db.session.execute(query).scalars().first()
        return prev.firm if prev else self.firm

    def to_dict(self):
        return {
            "id" : self.external_id,
            "name" : self.name,
            "name_length" : self.name_length(),
            "phone" : self.phone,
            "email" : self.email,
            "firm" : self.firm,
            "previous_firm": self.previous_firm(),
            "address" : self.address,
            "patents" : self.patents,
            "trademarks" : self.trademarks
        }

    def __repr__(self):
        return f'<Attorney {self.name}>'

    def __eq__(self, other):
        # For determining if two Attorney records from different dates are unchanged
        if not isinstance(other, Attorney):
            return NotImplemented
        return (
            self.external_id == other.external_id and
            self.name == other.name and
            (self.phone or None) == (other.phone or None) and
            (self.email or None) == (other.email or None) and
            (self.firm or None) == (other.firm or None) and
            (self.address or None) == (other.address or None) and
            bool(self.patents) == bool(other.patents) and
            bool(self.trademarks) == bool(other.trademarks)
        )

class Firm(db.Model, PaginatedAPIMixin):
    __tablename__ = 'firms'
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    external_id: so.Mapped[Optional[str]] = so.mapped_column(sa.String(36), index=True)  # UUID format
    name: so.Mapped[str] = so.mapped_column(sa.String(128), index=True)
    phone: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32))
    email: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120), index=True)
    website: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120), index=True)
    directors: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256), index=True)
    address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128))
    patents: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    trademarks: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)

    attorneys: so.Mapped[list["Attorney"]] = so.relationship(back_populates="firm_record")

    def to_dict(self):
        return {
            "id" : self.external_id,
            "name" : self.name,
            "phone" : self.phone,
            "email" : self.email,
            "website" : self.website,
            "address" : self.address,
            "patents" : self.patents,
            "trademarks" : self.trademarks
        }

    def __repr__(self):
        return f'<Firm {self.name}>'

    def __eq__(self, other):
        # For determining if two Attorney records from different dates are unchanged
        if not isinstance(other, Firm):
            return NotImplemented
        return (
            self.external_id == other.external_id and
            self.name == other.name and
            (self.phone or None) == (other.phone or None) and
            (self.email or None) == (other.email or None) and
            (self.website or None) == (other.website or None) and
            (self.directors or None) == (other.directors or None) and
            (self.address or None) == (other.address or None) and
            bool(self.patents) == bool(other.patents) and
            bool(self.trademarks) == bool(other.trademarks)
        )

    def attorney_count(self):
        return len(self.attorneys)
