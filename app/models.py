from typing import Optional
import sqlalchemy as sa
import sqlalchemy.orm as so
from app import db

class Attorney(db.Model):
    __tablename__ = 'attorneys'
    id: so.Mapped[int] = so.mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    external_id: so.Mapped[str] = so.mapped_column(sa.String(36), index=True)  # UUID format
    name: so.Mapped[str] = so.mapped_column(sa.String(64), index=True)
    phone: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32))
    email: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120), index=True)
    firm: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128), index=True)
    address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128))
    patents: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    trademarks: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    valid_from: so.Mapped[sa.Date] = so.mapped_column(sa.Date, index=True)
    valid_to: so.Mapped[Optional[sa.Date]] = so.mapped_column(sa.Date, index=True)

    def __repr__(self):
        return f'<Attorney {self.name}>'

class Firm(db.Model):
    __tablename__ = 'firms'
    id: so.Mapped[int] = so.mapped_column(primary_key=True, autoincrement=True)
    external_id: so.Mapped[str] = so.mapped_column(sa.String(36), index=True)  # UUID format
    name: so.Mapped[str] = so.mapped_column(sa.String(128), index=True)
    phone: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32))
    email: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120), index=True)
    website: so.Mapped[Optional[str]] = so.mapped_column(sa.String(120), index=True)
    directors: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256), index=True)
    address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(128))
    patents: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    trademarks: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    valid_from: so.Mapped[sa.Date] = so.mapped_column(sa.Date, index=True)
    valid_to: so.Mapped[Optional[sa.Date]] = so.mapped_column(sa.Date, index=True)

    def __repr__(self):
        return f'<Firm {self.name}>'