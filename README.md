# maps

This repository provides tools for building geographic visualizations and a
complete data pipeline for real-time client reporting.  It includes sample
scripts for stand‑alone heatmaps as well as a modular pipeline supporting data
ingestion, cleaning, modeling and interactive dashboards.

## Requirements

Install the required Python packages listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Installing geospatial dependencies

`geopandas` and its underlying library `fiona` depend on native tools such as
GDAL, GEOS and PROJ. These may need to be installed system wide before running
`pip install` if you are not using Conda. On Debian/Ubuntu systems you can run:

```bash
sudo apt-get install gdal-bin libgdal-dev libproj-dev libgeos-dev
pip install geopandas fiona
```

If you have Conda available, it can handle the compiled binaries for you:

```bash
conda install geopandas fiona
```

Several example scripts in this repository, such as
`spending_heatmap.py` and `choropleth_by_spend.py`, require these geospatial
libraries. They will fail to run until the dependencies above are installed.

### Sample ZIP archives

The example scripts reference two small ZIP files—`Recovery_Results.zip` and
`updated sheets and numbers May 19.zip`—which contain sample spreadsheets. These
archives are no longer included in the repository. Running
`client_spend_pipeline.py` will automatically download them from the URLs
embedded in the script. You can also fetch them manually from the project's
GitHub release page if you prefer to run the examples offline.

For quick testing of `choropleth_by_spend.py` without downloading large files,
run `generate_sample_inputs.py` to create a tiny shapefile and matching CSV. The
script outputs `sample_geometry.zip` and `sample_data.zip` in the current
directory, which you can then pass to the heatmap script.

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

If you generated the small test inputs with `generate_sample_inputs.py`, invoke
the script as follows:

```bash
python3 generate_sample_inputs.py
python3 choropleth_by_spend.py sample_geometry.zip sample_data.zip output.html \
    --geometry-zip-field ZCTA5CE10 --data-zip-field zip --spend-field spend
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

## Full data pipeline

The `pipeline` package implements a modular system for ingesting heterogeneous
data sources, cleaning and joining them by geography and time, running
anomaly-detection models, training supervised classifiers and serving
interactive Dash dashboards.

Running the pipeline requires providing a list of data files, a ZIP-to-DMA
mapping CSV and a shapefile for geographic boundaries:

```bash
python3 -m pipeline.main \
  --data-sources spend.csv visits.csv \
  --zip-dma-mapping zip_to_dma.csv \
  --geo-shapefile us_zips.shp
```

This command launches a dashboard at `http://127.0.0.1:8050` with choropleth
maps and scatter plots that update based on demographic filters.

## Client spend pipeline

`client_spend_pipeline.py` provides an end‑to‑end workflow that downloads the
client spreadsheets, aggregates spending by ZIP code and DMA, and generates a
self‑contained Mapbox HTML visualization. A Mapbox access token must be supplied
via the `MAPBOX_TOKEN` environment variable.

```bash
MAPBOX_TOKEN=<your_token> python3 client_spend_pipeline.py --output-html client_map.html
```

The script uses default URLs for the two zip archives and the ZIP‑to‑coordinate
CSV, so running the command above will create `client_map.html` with sample
data. Pass `--zip1`, `--zip2` or `--zip-latlon` to override these sources with
local paths or alternate links.

## Contributing

Install the `pre-commit` tool and set up the hooks so formatting and linting
run automatically on each commit:

```bash
pip install pre-commit
pre-commit install
```

The hooks invoke `black --line-length 79` and `flake8` to keep the codebase
consistent.
