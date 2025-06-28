import argparse
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(
        description="Create a US spending heatmap by ZIP code or DMA")
    parser.add_argument('spend_csv', help='CSV file with ZIP or DMA and spend data')
    parser.add_argument('shapefile', help='Shapefile with ZIP or DMA boundaries')
    parser.add_argument('--geo-key', help='Identifier column in the shapefile')
    parser.add_argument('--data-key', help='Identifier column in the CSV')
    parser.add_argument('--spend-field', default='spend', help='Column with spend values')
    parser.add_argument('--output', default='heatmap.png', help='Output image file')
    parser.add_argument('--states', help='Optional shapefile with state boundaries')
    args = parser.parse_args()

    # Load spending data
    data = pd.read_csv(args.spend_csv)

    # Load geographic boundaries
    geo = gpd.read_file(args.shapefile)

    # Determine the key columns for merging
    geo_key = args.geo_key
    if geo_key is None:
        if 'ZIP' in geo.columns:
            geo_key = 'ZIP'
        elif 'DMA' in geo.columns:
            geo_key = 'DMA'
        else:
            raise ValueError('Specify --geo-key; could not infer column name.')

    data_key = args.data_key
    if data_key is None:
        if 'ZIP' in data.columns:
            data_key = 'ZIP'
        elif 'DMA' in data.columns:
            data_key = 'DMA'
        else:
            raise ValueError('Specify --data-key; could not infer column name.')

    # Ensure join columns are strings for a robust merge
    geo[geo_key] = geo[geo_key].astype(str)
    data[data_key] = data[data_key].astype(str)

    # Merge spending data with geographic boundaries
    merged = geo.merge(data[[data_key, args.spend_field]],
                       left_on=geo_key, right_on=data_key, how='left')

    # Create the plot
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    merged.plot(column=args.spend_field,
                cmap='OrRd',
                linewidth=0.1,
                edgecolor='white',
                missing_kwds={
                    'color': 'lightgrey',
                    'edgecolor': 'white',
                    'label': 'No data'
                },
                legend=True,
                legend_kwds={'label': 'Total Spend ($)'},
                ax=ax)

    # Optionally overlay state boundaries
    if args.states:
        states = gpd.read_file(args.states)
        states.boundary.plot(ax=ax, color='black', linewidth=0.5)

    # Remove axes for a cleaner look
    ax.set_axis_off()

    # Set an appropriate title
    if 'zip' in data_key.lower():
        title = 'US Spending Heatmap by ZIP Code'
    else:
        title = 'US Spending Heatmap by DMA'
    ax.set_title(title)

    plt.tight_layout()
    plt.savefig(args.output, dpi=300)
    print(f'Saved heatmap to {args.output}')


if __name__ == '__main__':
    main()
