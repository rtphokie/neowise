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


def neowise(lat, lon, month, day, hour, tzname,  minute=0, sunaltmax=-12.0, comet='C/2020 F3 (NEOWISE)'):
    thistz = timezone(tzname)
    now_there = datetime.datetime.now(thistz)
    offset = now_there.utcoffset().total_seconds() / 60 / 60
    # print (f"day {day} hour {hour}  / {hour-offset+2}")
    hour = hour-offset+2
    comet = sun + mpc.comet_orbit(comets.loc[comet], ts, GM_SUN)
    obs = earth + Topos(lat, lon)

    times = ts.utc(2020, month, day, hour, range(60*12))
    # print(times[0].astimezone(thistz))

    comet_alts, comet_azs = observe(comet, obs, times)
    sun_alts, sun_azs = observe(sun, obs, times)
    data = {'firstseen': {}, 'lastseen': {}}
    for (t, comet_az, comet_alt, sun_alt) in zip(times, comet_azs.degrees, comet_alts.degrees, sun_alts.degrees):
        # print(f"  {t.astimezone(thistz)} {comet_alt:.1f} {sun_alt:.1f}")
        if comet_alt > 0.0:
            # comet is above the horizon
            if sun_alt <= sunaltmax:
                # before/after nautical (-12) twilight/dusk
                if len(data['firstseen']) == 0:
                    data['firstseen']['time'] = t.astimezone(thistz)
                    data['firstseen']['az'] = comet_az
                    data['firstseen']['alt'] = comet_alt
                    data['firstseen']['sun_alt'] = sun_alt
                    # print(f"hi  {t.astimezone(thistz)} {comet_alt:.1f} {sun_alt:.1f}")
            else:
                # nautical dawn
                if len(data['firstseen']) > 0  and len(data['lastseen']) == 0 :
                    data['lastseen']['time'] = t.astimezone(thistz)
                    data['lastseen']['az'] = comet_az
                    data['lastseen']['alt'] = comet_alt
                    data['lastseen']['sun_alt'] = sun_alt
                    # print(f"bye {t.astimezone(thistz)} {comet_alt:.1f} {sun_alt:.1f}")
        else:
            # comet set after nautical dusk
            if len(data['firstseen']) > 0 and len(data['lastseen']) == 0:
                data['lastseen']['time'] = t.astimezone(thistz)
                data['lastseen']['az'] = comet_az
                data['lastseen']['alt'] = comet_alt
                data['lastseen']['sun_alt'] = sun_alt
                # print(f"bye {t.astimezone(thistz)} {comet_alt:.1f} {sun_alt:.1f}")
    return data



def observe(object, obs, times):
    astrometric = obs.at(times).observe(object)
    apparent = astrometric.apparent()
    alts, azs, distances = apparent.altaz()
    return alts, azs

def buildtable(lat, lng, tzname):
    str = f"<p>The comet will be most visible in the morning over the weekend before switching to better visibility in the evening early next week. YMMV</p>"
    str += f"<h3>Visibility of Comet C/2020 F3 (NEOWISE) for {lat}, {lng}</h3>\n"
    str += "<table border=1><tr><th rowspan=1>date</th>"
    str += "<th colspan=1>morning (low on NE horizon)</th>"
    str += "<th colspan=1>evening (low on NW horizon)</th>"
    str += "</tr>\n"
    for x in range(10, 18):
        str += f"<tr><td>7/{x}</td>"
        morning = neowise(lat, lng, 7, x, 0, tzname, sunaltmax=-x-3)
        if 'time' in morning['firstseen']:
            str += f"<td align='center'>{morning['firstseen']['time'].strftime('%-I:%M %p')}"
            str += f" - {morning['lastseen']['time'].strftime('%-I:%M %p')}<br>"
            str += f"<small>reaches {morning['lastseen']['alt']:.1f}&deg; above horizon</small>"
            str += "</td>"
        else:
            str += "<td align=center>not visible</td>"
        evening = neowise(lat, lng, 7, x, 12, tzname, sunaltmax=-x-3)
        if 'time' in evening['firstseen']:
            str += f" <td align='center'>{evening['firstseen']['time'].strftime('%-I:%M %p')}"
            try:
                str += f" - {evening['lastseen']['time'].strftime('%-I:%M %p')}<br>"
                str += f"<small>appears {evening['firstseen']['alt']:.1f}&deg; above horizon</small>"
                str += "</td>"
            except:
                str += f" - stays up until nautical dawn<br>"
                str += f"<small>appears {evening['firstseen']['alt']:.1f}&deg; above horizon</small>"
            str += "<tr>\n"
        else:
            str += "<td align=center>not visible</td>"
    str += "</table>\n"
   
    return str


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
