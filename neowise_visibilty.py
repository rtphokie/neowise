from pprint import pprint
import unittest
from skyfield.api import Loader, Topos
from skyfield.data import mpc
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
from pytz import timezone
import datetime

load = Loader('/var/data')
eph = load('de421.bsp')
ts = load.timescale(builtin=True)
sun, earth = eph['sun'], eph['earth']
with load.open(mpc.COMET_URL) as f:
    comets = mpc.load_comets_dataframe(f)
comets = comets.set_index('designation', drop=False)


def comet_visibility(start_dt, comet_name, lat, lng, tz='UTC', days=1, min_comet_alt=0, max_sun_alt=-12):
    # get comet ephemris and observer's location in space
    comet = sun + mpc.comet_orbit(comets.loc[comet_name], ts, GM_SUN)
    obs = earth + Topos(lat, lng)

    # build list of minutes
    times = ts.utc(start_dt.year, start_dt.month, start_dt.day, start_dt.hour, range(60*24*days)) 

    # calculate comet and sun positions into lists of altitudes and azimuths for the comet and Sun
    comet_alts, comet_azs, _ = observe(comet, obs, times) # position of comet from observers POV in alt/az
    sun_alts, sun_azs, _ = observe(sun, obs, times) # position of Sun from observers POV in alt/az

    # combine resulting lists
    data = {'comet_alt': comet_alts.degrees, 'comet_az': comet_azs.degrees,
            'sun_alt': sun_alts.degrees, 'sun_az': sun_azs.degrees}
    if not all(v == len(times) for v in [len(list(x)) for x in data.values()]):
        raise ValueError ("time and alt/az position lists for the comet and Sun are different sizes")
    data['time'] = times.astimezone(timezone(tz))
    df = pd.DataFrame.from_dict(data)

    # filter out times where the comet is below the horizon or the sky is too bright
    df_visible = df[(df.comet_alt > min_comet_alt) & (df.sun_alt < max_sun_alt)]
    df_visible['delta_sec'] = [x.total_seconds() for x in df_visible.time.diff()]

    # find
    instances = []
    instance = None
    for index, row in df_visible.iterrows():
        if row['delta_sec'] != 60:
            row['comet_az_cardinal'] = degrees_to_cardinal(row['comet_az'])
            if instance != None:
                instance['end'] = prevrow.to_dict()
            instance={'begin': row.to_dict()}
            instances.append(instance)
        prevrow = row.copy()
    instance['end'] = prevrow.to_dict() # last row is setting of last instance

    for instance in instances:
        instance['duration'] = instance['end']['time'] - instance['begin']['time']

    return(df_visible, instances)


def observe(object, obs, times):
    astrometric = obs.at(times).observe(object)
    apparent = astrometric.apparent()
    alts, azs, distances = apparent.altaz()
    return alts, azs

def degrees_to_cardinal(d):
    dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    ix = round(d / (360. / len(dirs)))
    return dirs[ix % len(dirs)]

class MyTestCase(unittest.TestCase):
    def test_CDT(self):
        print ("bowling green, CDT")
        lat="36.96 N"
        lng = "86.49 W"
        tz = 'US/Central'
        morning = neowise(lat, lng, 7, 10, 0, tz, sunaltmax=-12)
        self.assertEqual(3, morning['firstseen']['time'].hour)
        evening = neowise(lat, lng, 7, 10, 12, tz, sunaltmax=-12)
        self.assertEqual(len(evening['firstseen']), 0)
        text = buildemail(lat, lng, tz)

    def test_EDT(self):
        print ("Myrtle Beach, EDT")
        lat = '33.8 N'
        lng = '79.0 W'
        tz = 'US/Eastern'
        morning = neowise(lat, lng, 7, 11, 0, tz, sunaltmax=-12)
        self.assertEqual(4, morning['firstseen']['time'].hour)
        evening = neowise(lat, lng, 7, 16, 12, tz, sunaltmax=-12)
        self.assertEqual(21, evening['firstseen']['time'].hour)
        text = buildemail(lat, lng, tz)

    def test_pdt(self):
        print ("Oxnard, PDT")
        lat = '34.8 N'
        lng = '119.18 W'
        tz = 'US/Pacific'
        morning = neowise(lat, lng, 7, 11, 0, tz, sunaltmax=-12)
        self.assertEqual(3, morning['firstseen']['time'].hour)
        evening = neowise(lat, lng, 7, 16, 12, tz, sunaltmax=-12)
        self.assertEqual(21, evening['firstseen']['time'].hour)
        text = buildemail(lat, lng, tz)

    def test_edt_north(self):
        # WBZ Boston, MA 42.36 - 71.13
        lat="42.36 N"
        lng = "71.13 W"
        tz = 'US/Eastern'
        morning = neowise(lat, lng, 7, 11, 0, tz, sunaltmax=-14)
        self.assertEqual(2, morning['firstseen']['time'].hour)
        evening = neowise(lat, lng, 7, 14, 12, tz, sunaltmax=-12)
        self.assertEqual(21, evening['firstseen']['time'].hour)
        morning = neowise(lat, lng, 7, 16, 0, tz, sunaltmax=-14)
        self.assertEqual(2, morning['firstseen']['time'].hour)
        evening = neowise(lat, lng, 7, 17, 12, tz, sunaltmax=-12)
        self.assertEqual(21, evening['firstseen']['time'].hour)
        text = buildemail(lat, lng, tz)



if __name__ == '__main__':
    unittest.main()
