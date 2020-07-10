# neowise
calculating the position of comet C/2020 F3 (NEOWISE) relative to nautical twlight/dusk

## requires
* Skyfield
* pandas

## methodology
Visibility estimates are based on my observations the morning of 2020-07-10 from a rural, reasonably dark location this morning of both the comet (and nearby stars of known brightness for comparison purposes), 
I lost sight of the comet right at nautical dawn (when the Sun is 12&deg; below the horizon).Calculations are based on published ephemeris from JPL and the IAU Minor Planet Center. "
To account for the expected dimming over the next week, I'm subtracting an additional degree each day from today's nautical dawn/dusk starting point (Sat -13, Sun -14, and so on). "

This approach is far from perfect but should help set expecations and plan observing.
