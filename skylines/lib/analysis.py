# -*- coding: utf-8 -*-

import os
import datetime
import simplejson
from sqlalchemy.sql.expression import and_
from skylines import files
from tg import config
from skylines.model.geo import Location
from skylines.model import DBSession, Airport, Trace, FlightPhase
import logging

log = logging.getLogger(__name__)


def helper_path(helper):
    return os.path.join(config['skylines.analysis.path'], helper)


def read_location(node):
    """
    Reads the latitude and longitude attributes of the node
    and returns a Location instance if the node was parsed correctly.
    """

    if node is None:
        return None

    if 'latitude' not in node or 'longitude' not in node:
        return None

    try:
        latitude = float(node['latitude'])
        longitude = float(node['longitude'])
        return Location(latitude=latitude, longitude=longitude)
    except ValueError:
        return None


def import_location_attribute(node, name):
    """
    Reads a Location instance from an attribute of the node
    with the given name.
    """

    if node is None or name not in node:
        return None

    location = node[name]
    return read_location(location)


def import_datetime_attribute(node, name):
    if node is None or name not in node:
        return None
    try:
        return datetime.datetime.strptime(node[name], '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        return None


def find_contest(root, name):
    if 'contests' not in root:
        return None

    if name not in root['contests']:
        return None

    return root['contests'][name]


def find_trace(contest, name):
    if not name in contest:
        return None

    return contest[name]


def read_time_of_day(turnpoint, flight):
    if 'time' not in turnpoint:
        return None

    time = int(turnpoint['time'])
    time = datetime.timedelta(seconds=time)

    time = datetime.datetime.combine(flight.takeoff_time.date(),
                                     datetime.time(0, 0, 0)) + time

    return time


def delete_trace(contest_name, trace_name, flight):
    q = DBSession.query(Trace) \
        .filter(and_(Trace.flight == flight,
                     Trace.contest_type == contest_name,
                     Trace.trace_type == trace_name))
    q.delete()


def save_trace(contest_name, trace_name, node, flight):
    delete_trace(contest_name, trace_name, flight)

    if 'turnpoints' not in node:
        return

    locations = []
    times = []
    for turnpoint in node['turnpoints']:
        location = read_location(turnpoint)
        time = read_time_of_day(turnpoint, flight)

        if location is None or time is None:
            continue

        locations.append(location)
        times.append(time)

    if len(locations) < 2 or len(times) < 2:
        return

    trace = Trace()
    trace.contest_type = contest_name
    trace.trace_type = trace_name
    trace.locations = locations
    trace.times = times

    if 'duration' in node:
        trace.duration = datetime.timedelta(seconds=int(node['duration']))

    if 'distance' in node:
        trace.distance = int(node['distance'])

    flight.traces.append(trace)


def save_contest(contest_name, traces, flight):
    for trace_name, trace in traces.iteritems():
        save_trace(contest_name, trace_name, trace, flight)


def save_contests(root, flight):
    if 'contests' not in root or flight.takeoff_time is None:
        # The takeoff_time is needed to convert the
        # time integer to a DateTime instance
        return

    for contest_name, traces in root['contests'].iteritems():
        save_contest(contest_name, traces, flight)


def save_takeoff(event, flight):
    flight.takeoff_time = import_datetime_attribute(event, 'time')
    flight.takeoff_location = read_location(event)
    if flight.takeoff_location is not None:
        flight.takeoff_airport = Airport.by_location(flight.takeoff_location)


def save_landing(event, flight):
    flight.landing_time = import_datetime_attribute(event, 'time')
    flight.landing_location = read_location(event)
    if flight.landing_location is not None:
        flight.landing_airport = Airport.by_location(flight.landing_location)


def save_events(events, flight):
    if 'takeoff' in events:
        save_takeoff(events['takeoff'], flight)
    if 'landing' in events:
        save_landing(events['landing'], flight)


def save_phases(root, flight):

    if 'phases' not in root or 'performance' not in root:
        return

    phases = []

    PT_IDX = {'powered': FlightPhase.PT_POWERED,
              'cruise': FlightPhase.PT_CRUISE,
              'circling': FlightPhase.PT_CIRCLING}

    CD_IDX = {'': None,
              'left': FlightPhase.CD_LEFT,
              'mixed': FlightPhase.CD_MIXED,
              'right': FlightPhase.CD_RIGHT,
              'total': FlightPhase.CD_TOTAL}


    for phdata in root['phases']:
        ph = FlightPhase()
        ph.flight = flight
        ph.aggregate = False
        ph.start_time = import_datetime_attribute(phdata, 'start_time')
        ph.end_time = import_datetime_attribute(phdata, 'end_time')
        ph.phase_type = PT_IDX[phdata['type']]
        ph.circling_direction = CD_IDX[phdata['circling_direction']]
        ph.alt_diff = phdata['alt_diff']
        ph.duration = datetime.timedelta(seconds=phdata['duration'])
        ph.distance = phdata['distance']
        ph.speed = phdata['speed']
        ph.vario = phdata['vario']
        ph.glide_rate = phdata['glide_rate']
        ph.count = 1

        phases.append(ph)

    for statname in ["total", "left", "right", "mixed"]:
        phdata = root['performance']["circling_%s" % statname]
        ph = FlightPhase()
        ph.aggregate = True
        ph.phase_type = FlightPhase.PT_CIRCLING
        ph.fraction = round(phdata['fraction'] * 100)
        ph.circling_direction = CD_IDX[statname]
        ph.alt_diff = phdata['alt_diff']
        ph.duration = datetime.timedelta(seconds=phdata['duration'])
        ph.vario = phdata['vario']
        ph.count = phdata['count']

        phases.append(ph)

    phdata = root['performance']['cruise_total']
    ph = FlightPhase()
    ph.aggregate = True
    ph.phase_type = FlightPhase.PT_CRUISE
    ph.circling_direction = FlightPhase.CD_TOTAL
    ph.alt_diff = phdata['alt_diff']
    ph.duration = datetime.timedelta(seconds=phdata['duration'])
    ph.fraction = round(phdata['fraction'] * 100)
    ph.distance = phdata['distance']
    ph.speed = phdata['speed']
    ph.vario = phdata['vario']
    ph.glide_rate = phdata['glide_rate']
    ph.count = phdata['count']

    phases.append(ph)

    flight._phases = phases

def analyse_flight(flight):
    path = files.filename_to_path(flight.igc_file.filename)
    log.info('Analyzing ' + path)

    root = None
    with os.popen(helper_path('AnalyseFlight') + ' "' + path + '"') as f:
        try:
            root = simplejson.load(f)
        except simplejson.JSONDecodeError:
            log.error('Parsing the output of AnalyseFlight failed.')

            if log.isEnabledFor(logging.DEBUG):
                with os.popen(helper_path('AnalyseFlight') + ' "' + path + '"') as f_debug:
                    log.debug(helper_path('AnalyseFlight') +
                              ' "' + path + '" = ' + str(f_debug.readlines()))

            return False

    if not root:
        return False

    if 'events' in root:
        save_events(root['events'], flight)

    contest = find_contest(root, 'olc_plus')
    if contest is not None:
        trace = find_trace(contest, 'classic')
        if trace is not None and 'distance' in trace:
            flight.olc_classic_distance = int(trace['distance'])
        else:
            flight.olc_classic_distance = None

        trace = find_trace(contest, 'triangle')
        if trace is not None and 'distance' in trace:
            flight.olc_triangle_distance = int(trace['distance'])
        else:
            flight.olc_triangle_distance = None

        trace = find_trace(contest, 'plus')
        if trace is not None and 'score' in trace:
            flight.olc_plus_score = int(trace['score'])
        else:
            flight.olc_plus_score = None

    save_contests(root, flight)
    save_phases(root, flight)

    flight.needs_analysis = False
    return True


def flight_path(igc_file, max_points = 1000):
    path = files.filename_to_path(igc_file.filename)
    f = os.popen(helper_path('FlightPath') + ' --max-points=' + str(max_points) + ' "' + path + '"')

    path = []
    for line in f:
        line = line.split()
        path.append((int(line[0]), float(line[1]), float(line[2]), int(line[3]), int(line[4])))
    return path
