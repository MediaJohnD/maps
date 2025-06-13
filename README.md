# maps

This repository contains a simple script to build ZIP code choropleth maps.

## Requirements

Install the required Python packages:

```bash
pip install geopandas matplotlib folium pandas
```

## Usage

The `choropleth_by_spend.py` script expects two zip files. These can be local
paths or direct HTTP(S) links (e.g. to raw files on GitHub):

1. **Geometry zip** – a zipped shapefile containing ZIP code geometries.
2. **Data zip** – a zipped CSV file with spending data. The CSV must contain a
   zip code column and a spend column.

To create a heatmap:

```bash
python3 choropleth_by_spend.py path/to/geometry.zip path/to/data.zip output.html \
    --geometry-zip-field ZCTA5CE10 --data-zip-field zip --spend-field spend
    --states path/to/us_states.shp
```

Remote URLs work too:

```bash
python3 choropleth_by_spend.py \
  https://raw.githubusercontent.com/user/repo/main/geometry.zip \
  https://raw.githubusercontent.com/user/repo/main/data.zip \
  output.html
```

The resulting `output.html` is an interactive choropleth showing spend by ZIP
code. Areas with missing spend data are rendered in light gray. Use the optional
`--states` argument to overlay state boundaries for reference.

## Static heatmap using GeoPandas

`spending_heatmap.py` creates a static PNG image of total spend by ZIP code or DMA using GeoPandas and Matplotlib. The script expects a CSV file with a spend column and a shapefile with the matching geographic boundaries.

```bash
python3 spending_heatmap.py spend_data.csv us_zips.shp --geo-key ZCTA5CE10 --data-key ZIP --spend-field spend --output heatmap.png
```

The output `heatmap.png` includes a legend labelled "Total Spend ($)". Optional
arguments allow specifying the key columns if they differ and overlaying state
boundaries with `--states path/to/states.shp`.
