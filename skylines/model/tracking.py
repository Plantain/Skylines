# -*- coding: utf-8 -*-

from datetime import datetime
from sqlalchemy.orm import relation
from sqlalchemy import Column, ForeignKey, Index
from sqlalchemy.types import Integer, Float, DateTime
from sqlalchemy.dialects.postgresql import INET
from geoalchemy.geometry import GeometryColumn, Point, GeometryDDL
from geoalchemy.postgis import PGComparator
from skylines.model.auth import User
from skylines.model import DeclarativeBase, DBSession
from skylines.model.geo import Location


class TrackingFix(DeclarativeBase):
    __tablename__ = 'tracking_fixes'

    id = Column(Integer, autoincrement=True, primary_key=True)

    time = Column(DateTime, nullable=False, default=datetime.utcnow)

    location_wkt = GeometryColumn('location', Point(2), comparator=PGComparator)

    track = Column(Integer)
    ground_speed = Column(Float)
    airspeed = Column(Float)
    altitude = Column(Integer)
    vario = Column(Float)
    engine_noise_level = Column(Integer)

    pilot_id = Column(Integer,
                      ForeignKey('tg_user.user_id', use_alter=True,
                                 name="tg_user.user_id"), nullable=False)

    pilot = relation('User', primaryjoin=(pilot_id == User.user_id))

    ip = Column(INET)

    @property
    def location(self):
        if self.location_wkt is None:
            return None

        wkt = DBSession.scalar(self.location_wkt.wkt)
        return Location.from_wkt(wkt)

    @location.setter
    def location(self, location):
        self.location_wkt = location.to_wkt()

Index('tracking_fixes_pilot_time', TrackingFix.pilot_id, TrackingFix.time)
GeometryDDL(TrackingFix.__table__)
