from datetime import datetime
from sqlalchemy import ForeignKey, Column
from sqlalchemy.orm import relation, backref
from sqlalchemy.types import String, Boolean, Numeric, Integer, DateTime, Interval
from skylines.model import DeclarativeBase
from skylines.model.flight import Flight


class FlightPhase(DeclarativeBase):
    __tablename__ = 'flight_phases'

    # Flight phase types
    PT_POWERED=1
    PT_CRUISE=2
    PT_CIRCLING=3

    # Circling directions
    CD_LEFT=1
    CD_MIXED=2
    CD_RIGHT=3
    CD_TOTAL=4

    id = Column(Integer, primary_key=True, autoincrement=True)
    flight_id = Column(Integer, ForeignKey('flights.id', ondelete='CASCADE'),
                       nullable=False, index=True)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    flight = relation('Flight', primaryjoin=(flight_id == Flight.id),
                      backref=backref('_phases', order_by=start_time,
                                      cascade='all,delete-orphan',
                                      passive_deletes=True))
    aggregate = Column(Boolean, nullable=False)
    phase_type = Column(Integer)  # see PT_* constants
    circling_direction = Column(Integer)  # see CD_* constants
    alt_diff = Column(Integer)
    duration = Column(Interval)
    fraction = Column(Integer)
    distance = Column(Integer)
    speed = Column(Numeric)
    vario = Column(Numeric)
    glide_rate = Column(Numeric)
    count = Column(Integer, nullable=False)
