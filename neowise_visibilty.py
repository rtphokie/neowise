from pprint import pprint
import unittest
from skyfield.api import Loader, Topos
from skyfield.data import mpc
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
import pandas as pd
import os
import numpy as np
from pytz import timezone
import datetime
import simple_cache
import time
import redis
import pickle

load = Loader('/var/data')
eph = load('de421.bsp')
ts = load.timescale(builtin=True)
sun, earth = eph['sun'], eph['earth']
with load.open(mpc.COMET_URL) as f:
    comets = mpc.load_comets_dataframe(f)
comets = comets.set_index('designation', drop=False)
UTC = timezone('UTC')
# LONGTTL=86400*30
# SHORTTTL=86400
LONGTTL=86400/2
SHORTTTL=86400/12
rconn = redis.StrictRedis(host='134.209.169.157', password="UCc6mrNpmdahGWd3mf8W")


def degrees_to_cardinal(d):
    dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    ix = round(d / (360. / len(dirs)))
    return dirs[ix % len(dirs)]


def comet_visibility(start_dt, comet_name, lat, lng, tzname='UTC',
                     minutes_coarse=60, minutes_fine=1,
                     days=1, min_comet_alt=0, max_sun_alt=-12):
    '''
    find periods where the comet is above the specified horizon and the Sun is sufficiently below the horizon

    :param start_dt: timezone aware datetime to begin search
    :param comet_name: string containing the comet name, must match up with the MPC database
    :param lat: string with a float followed by N or S (e.g. 35.22 N), no negative numbers
    :param lng: string with a float followed by E or W (e.g. 78.01 W), no negative numbers
    :param tzname: string containing the timzone name
    :param days: integer with the length of the search window in days
    :param min_comet_alt: minimum altitude the comet is visible, defaults to 0 but could be set to match treeline
    :param max_sun_alt: maximum Sun altitide, defaults to -12 (nautical twilight) which works for low altitude comets less than magnitude 2
           subtract 1-1.5 for that maximum altitude for every additional increase of 1 in magnitude.
    :return: a dataframe containing each minute during the specified time period the comet is observable
    '''
    rediskey=f"cv:{start_dt.isoformat()}:{days}:{lat}:{lng}".replace(' ', "_")
    start_utc = start_dt.astimezone(UTC) - datetime.timedelta(hours=4)
    try:
        cached_dict = pickle.loads(rconn.get(rediskey))
        print("from cv cache")
        return cached_dict
    except Exception as e:
        pass

    try:
        localtz = start_dt.tzinfo
    except:
        localtz = 'UTC'

    # get comet ephemris and observer's location in space
    comet = sun + mpc.comet_orbit(comets.loc[comet_name], ts, GM_SUN)
    obs = earth + Topos(lat, lng)

    # course grained look at visiblity, use Sun at horizon to ensure we dont miss any opporunities
    times_coarse= ts.utc(start_utc.year, start_utc.month, start_utc.day, start_utc.hour, range(0, 60 * 24 * days, minutes_coarse))
    _, instances = run_calculations(comet, 0, 0, obs, minutes_coarse, times_coarse)

    # rerun observations with a finer grain (defaults to 1 minute intervals) and passed Sun altitude
    instances_fine = []
    for instance in instances:
        new_start = instance['begin']['time']
        window = range(new_start.minute - minutes_coarse, round(instance['duration'].total_seconds() / 60) + minutes_coarse)
        times_fine = ts.utc(new_start.year, new_start.month, new_start.day, new_start.hour, window)
        _, local_instances_fine = run_calculations(comet, max_sun_alt, min_comet_alt, obs, minutes_fine, times_fine)
        instances_fine+=local_instances_fine
    daily_instances = dict()
    for instance in instances_fine:
        for x in ['begin', 'end']:
            instance[x]['tz'] = localtz
            instance[x]['time_local'] = instance[x]['time'].astimezone(localtz)
        datestr = instance['begin']['time_local'].strftime('%a %b %-d')
        if datestr not in daily_instances.keys():
            daily_instances[datestr] = []
        daily_instances[datestr].append(instance)

    pickled_object = pickle.dumps(daily_instances)
    rconn.set(rediskey, pickled_object)

    # rconn.lset("rediskey", daily_instances)

    return(daily_instances)


def run_calculations(comet_name, max_sun_alt, min_comet_alt, obs, step, times):
    '''
    generates a list of metadata on periods when the comet is visible
    :param comet_name: string containing the comet name, must match up with the MPC database
    :param min_comet_alt: minimum altitude the comet is visible, defaults to 0 but could be set to match treeline
    :param max_sun_alt: maximum Sun altitide, defaults to -12 (nautical twilight)
    :param obs: observer's topographic (relative to Earth) position
    :param step: interval between times in minutes
    :param times: list of times to measure comet and Sun apparant positions from observer
    :return: list of dictionaries for begin and ends of observable periods
    '''
    # calculate comet and sun positions into lists of altitudes and azimuths for the comet and Sun
    comet_alts, comet_azs, _ = observe(comet_name, obs, times)  # position of comet from observers POV in alt/az
    sun_alts, sun_azs, _ = observe(sun, obs, times)  # position of Sun from observers POV in alt/az
    # combine resulting lists
    data = {'comet_alt': comet_alts.degrees, 'comet_az': comet_azs.degrees,
            'sun_alt': sun_alts.degrees, 'sun_az': sun_azs.degrees}
    if not all(v == len(times) for v in [len(list(x)) for x in data.values()]):
        raise ValueError("time and alt/az position lists for the comet and Sun are different sizes")
    data['time'] = times.astimezone(UTC)
    df = pd.DataFrame.from_dict(data)
    # filter out times where the comet is below the horizon or the sky is too bright
    df_visible = df[(df.comet_alt > min_comet_alt) & (df.sun_alt < max_sun_alt)]
    df_visible['delta_sec'] = [x.total_seconds() for x in df_visible.time.diff()]

    instances = []
    instance = None
    prevrow = None
    for index, row in df_visible.iterrows():
        if row['delta_sec'] != step * 60:
            row['comet_az_cardinal'] = degrees_to_cardinal(row['comet_az'])
            if instance != None:
                instance['end'] = prevrow.to_dict()
            instance = {'begin': row.to_dict()}
            instances.append(instance)
        prevrow = row.copy()
    if instance is not None:
        instance['end'] = prevrow.to_dict()  # last row is setting of last instance
    for instance in instances:
        instance['duration'] = instance['end']['time'] - instance['begin']['time']
    return df_visible, instances

def observe(object, obs, times):
    '''
    measure aparant positions of specified object from the observer at specified times
    :param object: body to observe, comet or Sun
    :param obs: observer's topocentric position
    :param times: list of times to do the observations
    :return: lists of aparant altitudes, azimuths and distances
    '''
    astrometric = obs.at(times).observe(object)
    apparent = astrometric.apparent()
    alts, azs, distances = apparent.altaz()
    return alts, azs, distances

def comet_html(lat, lng, tzname,days=3):
    timefmt = '%-I:%M %p'
    tzshort = None
    str = ''
    str += f"<h3>Visibility of Comet C/2020 F3 (NEOWISE)</h3>\n"
    str += "<table border=1 align=center>\n<tr><th rowspan=1>date</th>"
    str += "<th colspan=1>morning (low on NE horizon)</th>"
    str += "<th colspan=1>evening (low on NW horizon)</th>"
    str += "</tr>\n"
    today = datetime.datetime.now()
    midnight_today_local = timezone(tzname).localize(datetime.datetime(today.year, today.month, today.day))
    instances = comet_visibility(midnight_today_local, 'C/2020 F3 (NEOWISE)', lat, lng, days=days)
    for date, data in instances.items():
        if len(data) < 2:
            colspan=2
        else:
            colspan=1
        str += f"<tr><th>{date}</th>\n"
        if len(data) ==0:
           str += f"  <td colspan={colspan}>no visibility</td>\n"
        else:
            for instance in data:
                if not tzshort:
                    tzshort = instance['begin']['time_local'].strftime('%Z')
                str += f"  <td colspan={colspan} align=\"center\">"
                str += f"{instance['begin']['time_local'].strftime(timefmt)}"
                str += "&nbsp;to&nbsp;"
                str += f" {instance['end']['time_local'].strftime(timefmt)}<br><small>"
                str += f"altitude: {round(instance['begin']['comet_alt'],1)}&deg;"
                str += "&nbsp;to&nbsp;"
                str += f"{round(instance['end']['comet_alt'],1)}&deg;"
                str += "</small></td>\n"
        str += "</tr>\n"
    str += "</table>\n"

    return str, tzshort


if __name__ == '__main__':
    unittest.main()
