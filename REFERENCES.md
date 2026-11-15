# References

Everything Rehearsal Earth uses: datasets, NASA pages, papers, map imagery, software
libraries and other resources. The datasets are also listed, with the same identifiers, in
`app/data/sources.json`, which the page reads for its Sources station. Dates are when we
accessed or checked each item.

## Datasets

1. **NASA Shuttle Radar Topography Mission Global 1 arc second V003 (SRTMGL1)**
   NASA JPL (2013). NASA Shuttle Radar Topography Mission Global 1 arc second [Data set]. NASA Land
   Processes Distributed Active Archive Center, Sioux Falls, South Dakota, USA.
   <https://doi.org/10.5067/MEaSUREs/SRTM/SRTMGL1.003>. Accessed 2026-11-08.
   - Tiles used: S24W070 (Atacama), S21W069 (Altiplano), N19W156 (Mauna Kea), from
     `https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/SRTMGL1.003/` (NASA Earthdata login).
   - Coverage 60° N to 56° S, from the NASA CMR collection record:
     <https://cmr.earthdata.nasa.gov/search/concepts/C2763266360-LPCLOUD.html> (read 2026-11-14).
   - Used for: Earth slope and roughness (`app/data/terrain.json`).

2. **MODIS/Terra Land Surface Temperature/Emissivity 8-Day L3 Global 1km SIN Grid V061 (MOD11A2)**
   Wan, Z., Hook, S., Hulley, G. (2021). MODIS/Terra Land Surface Temperature/Emissivity 8-Day L3
   Global 1km SIN Grid V061 [Data set]. NASA Land Processes Distributed Active Archive Center, Sioux
   Falls, South Dakota, USA. <https://doi.org/10.5067/MODIS/MOD11A2.061>. Accessed 2026-11-08.
   - Accessed as a point sample through NASA AppEEARS: <https://appeears.earthdatacloud.nasa.gov/>
     (the AppEEARS request ID was not recorded).
   - Documentation: <https://appeears.earthdatacloud.nasa.gov/api/product/MOD11A2.061> and the MOD11
     User Guide V61, <https://lpdaac.usgs.gov/documents/715/MOD11_User_Guide_V61.pdf>.
   - Used for: Earth day–night swing and mean temperature (`app/data/thermal.json`).

3. **LRO Diviner Level 3 Gridded Data Product (GDR), bolometric temperature maps**
   Paige, D., Sullivan, M., Williams, J-P. (2022). Lunar Reconnaissance Orbiter Diviner Derived Data
   Bundle 1. NASA Planetary Data System. <https://doi.org/10.17189/wj0s-w188>. Accessed 2026-11-13.
   - Files: `dgdr_tbol_avg_cyl_20100121d_004_img` (day) and `dgdr_tbol_avg_cyl_20100107n_004_img`
     (night), with their `.lbl` and `.xml` labels, from
     <https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/2010/cylindrical/img/>.
   - Used for: Moon equator temperatures shown as extra references (`app/data/moon_thermal.json`);
     not used in any score.

4. **LOLA 5 m/pixel maps for candidate south pole landing sites: Site23 (Malapert massif)**
   NASA Goddard Space Flight Center, Planetary Geodesy Data Archive (PGDA). No dataset DOI was found;
   the README asks users to cite Barker et al. (2021), below.
   - Files: `Site23_final_adj_5mpp_surf.tif` (heights) and `Site23_final_adj_5mpp_slp.tif` (slope),
     from <https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site23/>.
   - README: <https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/README>.
   - Product page (slope uncertainty and share of interpolated pixels):
     <https://pgda.gsfc.nasa.gov/products/78>, "PGDA - High-Resolution LOLA Topography for Lunar South
     Pole Sites" (read 2026-11-14).
   - Used for: the Moon slope and roughness reference (`app/data/moon_terrain.json`).

5. **NIST Cryogenic Material Properties database (linear expansion fits)**
   National Institute of Standards and Technology (NIST), Cryogenics Technologies Group.
   <https://trc.nist.gov/cryogenics/materials/materialproperties.htm>. Fit coefficients copied 2026-11-09.
   - 6061-T6 aluminum: <https://trc.nist.gov/cryogenics/materials/6061%20Aluminum/6061_T6Aluminum_rev.htm>
   - 304 stainless steel: <https://trc.nist.gov/cryogenics/materials/304Stainless/304Stainless_rev.htm>
   - Ti-6Al-4V titanium: <https://trc.nist.gov/cryogenics/materials/Ti6Al4V/Ti6Al4V_rev.htm>
   - Used for: the beam expansion coefficients in Try it (`app/data/config.json`).

## NASA pages and reference values

6. **NASA NSSDC Mars Fact Sheet**, <https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html>
   (checked 2026-11-08). Average temperature about 214 K (−59 °C); surface gravity 3.73 m/s² mean and
   3.69 m/s² at the equator (the page uses 3.71 m/s², as given by the team).
7. **NASA NSSDC Moon Fact Sheet**, <https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html>
   (checked 2026-11-08). Surface gravity 1.62 m/s².
8. **NASA NSSDC Earth Fact Sheet**, <https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html>
   (checked 2026-11-08). Standard gravity 9.80665 m/s² (the page uses 9.81 m/s²).
9. **Environment Challenges for Exploration of the Moon** (conference slides). Minow, J. I., et al.
   (2008-01-23). NASA Marshall Space Flight Center. NTRS 20080013552.
   <https://ntrs.nasa.gov/citations/20080013552>; PDF:
   <https://ntrs.nasa.gov/api/citations/20080013552/downloads/20080013552.pdf>. Used for the Moon
   day–night swing reference of 300 K (about 400 K by day to under 100 K by night). The PDF (over
   10 MB) was not read; the values are as provided by the team.
10. **10 Things to Know About Planetary Analogs** (NASA Science web page).
    <https://science.nasa.gov/solar-system/planetary-analogs/10-things-to-know-about-planetary-analogs/>
    (read 2026-11-14). Validation benchmark for Atacama Desert and Haughton Crater.
11. **Atacama Rover Astrobiology Drilling Studies (ARADS)** (NASA web page).
    <https://www.nasa.gov/universe/atacama-rover-astrobiology-drilling-studies-arads/> (read 2026-11-14).
    Validation benchmark for Atacama Desert.
12. **NASA GIBS imagery: Blue Marble: Next Generation.** The satellite map's background tiles come from
    NASA's Global Imagery Browse Services (GIBS), Web Mercator tiles, zoom levels 0 to 8:
    `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`.
    Credit shown on the map: *"Imagery: NASA GIBS (Blue Marble: Next Generation), part of NASA's
    ESDIS"*, linking to the GIBS API page,
    <https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api>.

## Papers

13. Barker et al. (2021). *Improved LOLA elevation maps for south pole landing sites: Error estimates
    and their impact on illumination conditions.* <https://doi.org/10.1016/j.pss.2020.105119>
    (the citation the LOLA Site23 README asks for).
14. Williams et al. (2017). *The global surface temperatures of the Moon as measured by the Diviner
    Lunar Radiometer Experiment.* <https://doi.org/10.1016/j.icarus.2016.08.012> (listed in the
    Diviner collection label).
15. Bandfield et al. (2011). *Lunar surface rock abundance and regolith fines temperatures derived
    from LRO Diviner Radiometer data.* <https://doi.org/10.1029/2011JE003866> (listed in the Diviner
    collection label).
16. Tamppari, L. K., Anderson, R. M., Archer, D., et al. (2010). *McMurdo Dry Valleys, Antarctica - A
    Mars Phoenix Mission Analog.* NASA Technical Reports Server.
    <https://ntrs.nasa.gov/citations/20100003844>. Validation benchmark for Dry Valleys.
17. ten Kate, I. L., Armstrong, R., Bernhardt, B., et al. (2010). *Mauna Kea, Hawaii as an Analogue
    Site for Future Planetary Resource Exploration: Results from the 2010 ILSO-ISRU Field-Testing
    Campaign.* NASA Technical Reports Server. <https://ntrs.nasa.gov/citations/20110008363>.
    Validation benchmark for Mauna Kea.

## Other external resources

18. **SpaceRef article on Mars temperature**, <https://spaceref.com/?p=24443>. Second source for the
    Mars mean temperature (−60 °C, 213.15 K), shown next to the NASA value. The page returned HTTP 403
    on 2026-11-08 and could not be read; the value is as provided by the team.

## Software

Libraries the page loads from public CDNs (the only external code the page runs):

19. **Chart.js 4.4.1**: the charts. <https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js>
20. **Leaflet 1.9.4**: the satellite map.
    <https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js> and
    <https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css>

Python packages used by the data pipeline and the tests (versions in our environment):

21. **NumPy 2.5.4**: arrays, medians and percentiles.
22. **rasterio 1.5.2**: reading the GeoTIFF and elevation files.
23. **earthaccess 0.19.0**: searching and downloading SRTM tiles from NASA Earthdata (`pipeline/get_tile.py`).
24. **pytest 9.2.0**: the test suite.
25. **Microsoft Edge, Google Chrome or Chromium** (headless): used by the tests to open the page.

Everything else (the page's HTML, CSS and JavaScript, the night sky, the station icons and the rover
illustration) is our own work, with no image files and no other external resources.
