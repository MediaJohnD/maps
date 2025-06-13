import zipfile
import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

zips = [
    ("30301", (33.75, -84.39)),
    ("78701", (30.27, -97.74)),
    ("10001", (40.75, -73.99)),
    ("90001", (33.97, -118.25)),
    ("98101", (47.61, -122.33)),
]

polys = []
for z, (lat, lon) in zips:
    polys.append({
        "ZCTA5CE10": z,
        "geometry": Polygon([
            (lon - 0.05, lat - 0.05),
            (lon + 0.05, lat - 0.05),
            (lon + 0.05, lat + 0.05),
            (lon - 0.05, lat + 0.05),
        ])
    })

gdf = gpd.GeoDataFrame(polys, crs="EPSG:4326")
gdf.to_file("zips.shp")

with zipfile.ZipFile("sample_geometry.zip", "w") as zf:
    for ext in ["shp", "shx", "dbf", "cpg", "prj"]:
        zf.write(f"zips.{ext}")

# Create sample data csv
pdf = pd.DataFrame({"zip": [z for z, _ in zips], "spend": [100, 200, 150, 250, 180]})
pdf.to_csv("data.csv", index=False)

with zipfile.ZipFile("sample_data.zip", "w") as zf:
    zf.write("data.csv")

print("Generated sample_geometry.zip and sample_data.zip")
