# -*- coding: utf-8 -*-
"""V2_Dirty_Water_Project.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1qCcaF9bQsYaxNmMRFKB0zdvBiJO_0F6M
"""

import dash
from dash import dcc, html, callback_context
from dash.dependencies import Input, Output, State
import pandas as pd
import plotly.graph_objects as go
import geopandas as gpd
import numpy as np
import bisect
import plotly.colors
import plotly.tools as tools
from plotly.subplots import make_subplots
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib import patches
import matplotlib.gridspec as gridspec
import requests
import os
import gdown
import shutil
import pyheif
from PIL import Image
import piexif
import exifread
from datetime import datetime
import asyncio
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from flask import send_from_directory

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# Build the service client for Google Drive API
service = build('drive', 'v3', developerKey=GOOGLE_API_KEY)

# Function to download files using Google Drive API
def download_file(file_id, destination):
    request = service.files().get_media(fileId=file_id)
    fh = open(destination, 'wb')
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f'Download {int(status.progress() * 100)}%.')
    fh.close()

# Load the publicly available CSV data
geolabels_link = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vR9KmvTArEvOntjGpzFbpai7tfGCE4atG7cre5BiG_CEhMQw7cOo6bz-SmgJRY7rGCP7ERnRywkwiw7/pub?gid=402113435&single=true&output=csv'
geolabels = pd.read_csv(geolabels_link)

samples_link = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vR9KmvTArEvOntjGpzFbpai7tfGCE4atG7cre5BiG_CEhMQw7cOo6bz-SmgJRY7rGCP7ERnRywkwiw7/pub?gid=1821472518&single=true&output=csv'
samples = pd.read_csv(samples_link)

encampments_link = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vR9KmvTArEvOntjGpzFbpai7tfGCE4atG7cre5BiG_CEhMQw7cOo6bz-SmgJRY7rGCP7ERnRywkwiw7/pub?gid=1918593179&single=true&output=csv'
encampments = pd.read_csv(encampments_link)

# Download .csv containing the FileIDs of all Rain Gauge images
file_id = '1-2dUhmLQ2ZuPjKujhT0jk9VeIngFW7Qa'
output_rain_gauges = '/tmp/rain_gauges.csv'
download_file(file_id, output_rain_gauges)
rain_gauge_list = pd.read_csv(output_rain_gauges)

file_id = '1AjVURDitIpEtvEgGCAUiiIt6066jYEsD'
output_site_images = '/tmp/site_images.csv'
download_file(file_id, output_site_images)
site_image_list = pd.read_csv(output_site_images)

# Download Santa Rosa Creek GeoJSON
file_id = '1mDhGKaYsRv0Z8pGOVsxYKMmqIvNDhcMr'  # Google Drive file ID
output_geojson = '/tmp/SantaRosaCreek.geojson'
download_file(file_id, output_geojson)
srcreek_gdf = gpd.read_file(output_geojson)

os.makedirs('assets', exist_ok = True)

async def download_images():
    for i, file in rain_gauge_list.iterrows():
        file_name = file['file_name']
        file_id = file['file_id']
        output_rain_figures = f'assets/rain_figure_{file_name}'
        # download_file(file_id, output_rain_figures)
        await asyncio.to_thread(download_file, file_id, output_rain_figures)
        await asyncio.sleep(1)
    for i, file in site_image_list.iterrows():
        file_name = file['file_name']
        file_id = file['file_id']
        output_site_images = f'assets/site_image_{file_name}'
        # download_file(file_id, output_site_images)
        await asyncio.to_thread(download_file, file_id, output_site_images)
        await asyncio.sleep(1)

def dms_to_dd(dms):
    try:  # Accounting for multiple styles of coordinate entries
        dms = dms.replace(" ", "").replace("°", " ").replace("'", " ").replace('"', " ")
        parts = dms.split()
        dd = float(parts[0]) + float(parts[1])/60 + float(parts[2])/(60*60)
        if len(parts) > 3 and parts[3] in ('S','W'):
            dd *= -1
    except:  # The coordinate is already in DD
        dd = float(dms)
    return dd

# Convert Geolabels from DMS to decimal degrees for latitude/longitude
geolabels['Latitude'] = geolabels['Latitude'].apply(dms_to_dd)
geolabels['Longitude'] = geolabels['Longitude'].apply(dms_to_dd)

# Create DateTime column for encampments
encampments['Month'] = encampments['Month'].str.strip()
encampments['Month'] = pd.to_datetime(encampments['Month'], format='%B').dt.month
encampments['date'] = pd.to_datetime(encampments[['Year', 'Month', 'Day']])

# Convert 'HomelessnessScore' to numeric after replacing 'x' with 2
encampments['HomelessnessScore'] = encampments['HomelessnessScore'].replace('x', 2)
encampments['HomelessnessScore'] = pd.to_numeric(encampments['HomelessnessScore'], errors='coerce')

# Add lat/lon coordinates to Encampments
merged_encampments = encampments.merge(geolabels, left_on='EncampmentSite', right_on='Key')

# Remove spaces from 'SampleSite' values
samples['SampleSite'] = samples['SampleSite'].str.replace(' ', '', regex=False)

# Create DateTime column for sample sites
samples['Month'] = samples['Month'].str.strip()
samples['Month'] = pd.to_datetime(samples['Month'], format='%B').dt.month
samples['date'] = pd.to_datetime(samples[['Year', 'Month', 'Day']])

# Add lat/lon coordinates to Samples
merged = samples.merge(geolabels, left_on='SampleSite', right_on='Key')

# Replace no nickname values with sample site code
merged['Nickname'] = merged['Nickname'].fillna(merged['Key'])


sample_site_coordinates = {}

# Add sample sites and their coordinates to the dict
for site in merged['SampleSite'].unique():
    # Extract the Latitude and Longitude values for each water sample site
    lat_lon = merged[merged['SampleSite'] == site][['Latitude', 'Longitude']].iloc[0]
    sample_site_coordinates[site] = (lat_lon['Latitude'], lat_lon['Longitude'])

# Add encampment sites and their coordinates to the dict
for site in merged_encampments['EncampmentSite'].unique():
    # Extract the Latitude and Longitude values for each encampment site
    lat_lon = merged_encampments[merged_encampments['EncampmentSite'] == site][['Latitude', 'Longitude']].iloc[0]
    sample_site_coordinates[site] = (lat_lon['Latitude'], lat_lon['Longitude'])


# List of columns to clean
columns_to_clean = ["pH", "TEMP", "DO(mg/L)", "Conductivity(us/cm)", "Ecoli (MPN/100mL)", "Enterococcus", "D.O%", "Phosphorus", "HF183 (MPN/100mL)"]

# Accounts for 'ND' and '>' in numeric fields
for column in columns_to_clean:
    merged[column] = merged[column].fillna(-1)  # Fill NA values with -1
    merged[column] = merged[column].astype(str)  # Convert the column to string type
    merged[column] = merged[column].replace("ND", "-1")  # Replace "ND" with -1
    merged[column] = merged[column].str.replace(">", "", regex=False)  # Remove ">" character
    merged[column] = merged[column].fillna("-1")
    merged[column] = pd.to_numeric(merged[column], errors='coerce')  # Convert to numeric

# Gets the sorted unique dates for the water sample sites
unique_dates = sorted(merged['date'].unique())

min_date = min(unique_dates)
max_date = max(unique_dates)
date_range = pd.date_range(min_date, max_date)

def generate_rain_figures():
    for sample_date in unique_dates:
        rain_figures[sample_date] = ''
    for sample_date, _ in rain_figures.items():
      # Update the rain_figures dictionary with the path to the figure
      rain_figures[sample_date] = f'/assets/rain_figure_{sample_date.strftime("%Y-%m-%d")}.png'

def euclidean_distance(lat1, lon1, lat2, lon2):
    return ((lat1 - lat2)**2 + (lon1 - lon2)**2)**0.5

# Function to find the closest site from the dictionary
def find_closest_site(lat, lon, sample_sites_dict):
    closest_site = None
    min_distance = float('inf')

    for site, (site_lat, site_lon) in sample_sites_dict.items():
        # Calculate the Euclidean distance between the input coordinates and the current site
        distance = euclidean_distance(lat, lon, site_lat, site_lon)

        # Update the closest site if this distance is smaller
        if distance < min_distance:
            closest_site = site
            min_distance = distance

    return closest_site

rain_figures = {}

generate_rain_figures()

# Create a Dash app
app = dash.Dash(__name__)
server = app.server
# download_images()
asyncio.run(download_images())

color_dict = {
    0: 'rgba(255, 255, 255, .5)',  # No homeless
    1: 'rgba(27, 77, 62, .1)',  # Homeless
    2: 'rgba(0, 0, 0, 0)'  # Not monitored
}

description_dict = {0: 'Monitored but no homelessness', 1: 'Monitored and homelessness found', 2: 'Not monitored'}

# Color Key
color_ranges = {}

initial_rain_gauge = rain_figures.get(pd.Timestamp(unique_dates[0]))

# Check if the image exists
if not os.path.exists(initial_rain_gauge):
    initial_rain_gauge = None

app.layout = html.Div([
    html.Div(
        style={
            'backgroundColor': '#f0f0f0',
            'borderRadius': '10px',
            'padding': '10px',
            'width': '98%',
            'boxShadow': '0 4px 8px rgba(0, 0, 0, 0.2)',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'flex-start'
        },
        children=[
            html.Label('Select Date:', style={'fontSize': 24, 'textAlign': 'left', 'marginRight': '20px'}),
            html.Div(
                style={
                    'flex': '1',
                    'minWidth': '300px',
                    'marginLeft': '20px',
                    'marginRight': '20px'
                },
                children=[
                    dcc.Slider(
                        id='date-slider',
                        min=0,
                        max=len(unique_dates) - 1,
                        value=0,
                        marks={i: {'label': f"{pd.Timestamp(date).strftime('%b, %Y')}", 'style': {'whiteSpace': 'nowrap', 'color': 'Black'}} for i, date in enumerate(unique_dates)},
                        step=None,
                        updatemode='drag',
                        included=False,
                        vertical=False
                    )
                ]
            )
        ]
    ),
    html.Button('Start/Stop', id='start-button', n_clicks=0, style={'marginBottom': '10px'}),
    dcc.Interval(id='interval-component', interval=10 * 1000, max_intervals=0),
    html.Div([
        html.Div([
          html.Div(id='date-indicator',
                children=['Sample Date:'],
                style={
                  'backgroundColor': '#1976D2',
                  'borderRadius': '5px',
                  'padding': '4px 4px',
                  'fontSize': '16px',
                  'color': 'white',
                  'textAlign': 'center',
                  'fontWeight': 'bold',
                  'fontFamily': 'Helvetica'
              }),
            dcc.Graph(id='map', style={'width': '100%', 'height': '500px'}),
            dcc.Markdown(id='debug-output', style={'whiteSpace': 'pre-line'}),
            dcc.Store(id='zoom-level', data=12),
            dcc.Store(id='lat-lon', data={'lat': 38.45, 'lon': -122.7}),
        ], style={'width': '75%', 'display': 'inline-block'}),

        html.Div([
            dcc.Tabs(
                id='tabs',
                children=[
                    dcc.Tab(
                        label='Map Settings',
                        children=[
                            html.Div([
                                html.Img(
                                    id='rain-gauge',
                                    src=initial_rain_gauge,
                                    style={'width': '96%', 'display': 'block', 'paddingTop': '0px', 'paddingRight': '2px', 'paddingBottom': '10px', 'paddingLeft': '10px'}
                                ),
                                dcc.Dropdown(
                                    id='color-dropdown',
                                    options=[
                                        {'label': 'pH', 'value': 'pH'},
                                        {'label': 'TEMP', 'value': 'TEMP'},
                                        {'label': 'DO(mg/L)', 'value': 'DO(mg/L)'},
                                        {'label': 'Conductivity(us/cm)', 'value': 'Conductivity(us/cm)'},
                                        {'label': 'Phosphorus', 'value': 'Phosphorus'},
                                        {'label': 'Ecoli (MPN/100mL)', 'value': 'Ecoli (MPN/100mL)'},
                                        {'label': 'Enterococcus', 'value': 'Enterococcus'},
                                        {'label': 'HF183 (MPN/100mL)', 'value': 'HF183 (MPN/100mL)'}
                                    ],
                                    value='Ecoli (MPN/100mL)',
                                    style={'width': '98%', 'margin-left': '5px'}
                                ),
                                html.Div(
                                    id='color-key',
                                    style={'border': 'thin lightgrey solid', 'marginLeft': '10px', 'marginRight': '2px', 'padding': '10px', 'marginTop': '5px'}
                                )
                            ])
                        ],
                        style={
                            'fontSize': '12px',
                            'fontFamily': 'Helvetica',
                            'padding': '5px 10px',
                            'backgroundColor': '#2196F3',
                            'color': 'white',
                            'borderRadius': '5px',
                        },
                        selected_style={
                            'fontSize': '12px',
                            'fontFamily': 'Helvetica',
                            'backgroundColor': '#1976D2',
                            'color': 'white',
                            'fontWeight': 'bold',
                            'padding': '5px 10px',
                            'borderRadius': '5px',
                        }
                    ),
                    dcc.Tab(
                        label='Graphs',
                        children=[
                            html.Div(id="date-display",
                              style={
                                'padding': '10px',
                                'fontSize': '16px',
                                'color': 'darkblue',
                                'textAlign': 'center',
                                'fontWeight': 'bold',
                                'fontFamily': 'Helvetica'
                            }),
                            html.Div(id="water-flow-label",
                              children=['⬅ Water Flow Direction'],
                              style={
                                'padding': '0px',
                                'fontSize': '10px',
                                'color': 'darkblue',
                                'textAlign': 'center',
                                'fontFamily': 'Helvetica'
                            }),
                            dcc.Graph(
                                id='sample-date-graphs',
                                config={
                                    'scrollZoom': False,
                                    'displayModeBar': False,
                                    'showAxisDragHandles': False,
                                    'staticPlot': False
                                },
                                style={
                                    'width': '98%',
                                    'display': 'block',
                                    'padding': '0',
                                    'margin': '0',
                                    'height': '474px',
                                    'overflowY': 'auto'
                                }
                            )
                        ],
                        style={
                            'fontSize': '12px',
                            'fontFamily': 'Helvetica',
                            'padding': '5px 10px',
                            'backgroundColor': '#2196F3',
                            'color': 'white',
                            'borderRadius': '5px',
                        },
                        selected_style={
                            'fontSize': '12px',
                            'fontFamily': 'Helvetica',
                            'backgroundColor': '#1976D2',
                            'color': 'white',
                            'fontWeight': 'bold',
                            'padding': '5px 10px',
                            'borderRadius': '5px',
                        }
                    ),
                    dcc.Tab(
                        label='Site Data',
                        children=[
                            html.Div(id="site-info-display",
                              children=['Click on a site on the map to display data.'],
                              style={
                                'padding': '10px',
                                'fontSize': '16px',
                                'color': 'darkblue',
                                'textAlign': 'center',
                                'fontWeight': 'bold',
                                'fontFamily': 'Helvetica'
                            }),
                            html.Div(id='date-image-list', style={'height': '500px', 'overflow-y': 'scroll'}),
                            html.Div(
                                children=[
                                    html.Img(
                                        id='image',
                                        src=None,
                                        style={'width': '95%', 'padding': '20px', 'textAlign': 'center', 'objectFit': 'contain', 'padding': '0', 'margin': '0',}
                                    )
                                ],
                                style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center'}
                            )
                        ],
                        style={
                            'fontSize': '12px',
                            'fontFamily': 'Helvetica',
                            'padding': '5px 10px',
                            'backgroundColor': '#2196F3',
                            'color': 'white',
                            'borderRadius': '5px',
                        },
                        selected_style={
                            'fontSize': '12px',
                            'fontFamily': 'Helvetica',
                            'backgroundColor': '#1976D2',
                            'color': 'white',
                            'fontWeight': 'bold',
                            'padding': '5px 10px',
                            'borderRadius': '5px',
                        }
                    )
                ]
            )
        ], style={'width': '25%', 'display': 'inline-block', 'vertical-align': 'top'})
    ], style={'display': 'flex', 'flexDirection': 'row'}),
])


# Initialize a variable to keep track of the last clicked point
last_clicked_point = None

@app.callback(
    Output('color-key', 'children'),
    Input('color-dropdown', 'value')
)
def update_color_key(selected_param):
    color_descriptions = color_ranges.get(selected_param, [])
    spans = []
    for color, description in color_descriptions:
        spans.extend([
            html.Span(style={'display': 'inline-block', 'width': '20px', 'height': '20px', 'marginRight': '5px', 'backgroundColor': color}),
            html.Span(description),
            html.Br()
        ])
    return spans

@app.callback(
    Output('interval-component', 'max_intervals'),
    Input('start-button', 'n_clicks')
)
def start_cycle(n_clicks):
    if n_clicks % 2 == 0:
        return 0  # stop cycling
    else:
        return -1  # start cycling

# Define callback for the interval component
@app.callback(
    Output('date-slider', 'value'),
    Input('interval-component', 'n_intervals'),
    State('date-slider', 'value')
)
def update_slider(n_intervals, current_value):
    if n_intervals is None:
        # When the app starts, n_intervals is None, so we need to check for this
        return current_value
    elif n_intervals > 0:
        return (current_value + 1) % len(unique_dates)  # cycle through dates
    else:
        return current_value  # keep current value

# Define the callback to update the rain gauge image and date indicator
@app.callback(
    Output('rain-gauge', 'src'),
    Output('date-indicator', 'children'),
    Input('date-slider', 'value')
)
def update_rain_gauge_and_date_indicator(selected_date_index):
    sample_date = unique_dates[selected_date_index]
    image_path = rain_figures.get(pd.Timestamp(sample_date))
    if image_path:
        return image_path, f"Sample Date: {sample_date.strftime('%Y-%m-%d')}"
    return None, f"Sample Date: {sample_date.strftime('%Y-%m-%d')}"

# Define the callback to update the date-specific graphs
@app.callback(
    Output('sample-date-graphs', 'figure'),
    Output('date-display', 'children'),
    Input('date-slider', 'value')
)
def update_sample_date_graphs(selected_date_index):
    sample_date = unique_dates[selected_date_index]
    filtered_df = merged[merged['date'] == sample_date]

    # Create a subplot grid with shared x-axis
    fig = make_subplots(rows=8, cols=1, shared_xaxes=True,
                        subplot_titles=("Ecoli (MPN/100mL)", "pH", "Phosphorus",
                                        "Conductivity(us/cm)", "DO(mg/L)", "D.O%", "Enterococcus", "HF183 (MPN/100mL)"))

    # Define each y-axis variable and corresponding title
    variables = [
        ("Ecoli (MPN/100mL)", "Ecoli (MPN/100mL)"),
        ("pH", "pH"),
        ("Phosphorus", "Phosphorus"),
        ("Conductivity(us/cm)", "Conductivity(us/cm)"),
        ("DO(mg/L)", "DO"),
        ("D.O%", "D.O%"),
        ('Enterococcus', 'Enterococcus'),
        ("HF183 (MPN/100mL)", "HF183 (MPN/100mL)")
    ]
  

    for i, (column, title) in enumerate(variables, start=1):
        # Filter out rows with No Data
        included_samples = filtered_df[filtered_df[column] != -1]

        included_samples['color'] = included_samples[column].apply(lambda value: map_colors(column, value))
        fig.add_trace(
            go.Scatter(
                x=included_samples['Longitude'],
                y=included_samples[column],
                mode="markers",
                marker=dict(color=included_samples['color']),
                name=title,
                text=included_samples.apply(lambda row: f"<b>{title}: {row[column]}</b><br>Sample Site: {row['SampleSite']}<br>Longitude: {row['Longitude']}<br>", axis=1),
                hoverinfo='text'
            ),
            row=i, col=1
        )
        fig.update_yaxes(title_text=title, title_font=dict(size=10), title_standoff=5, row=i, col=1)
        fig.update_xaxes(title_text="Longitude", showticklabels=True, row=i, col=1)

    fig.update_layout(height=1600, width=280, margin=dict(t=20, l=5, r=5), showlegend=False)

    return fig, f"Data Collected on {sample_date.strftime('%Y-%m-%d')}"

# This function takes the color brewer palette name and type (sequential or diverging) and
# returns a list of evenly spaced colors from that palette
def get_even_colors(palette, palette_type, num_colors):
    num_colors -= 1 # This accounts for "No Data" color, which is a transparent black
    # Sample num_colors evenly spaced colors from the given palette.
    if palette_type == 'sequential':
        palette_colors = getattr(plotly.colors.sequential, palette)
        palette_colors = palette_colors[2:] # Exclude the first 2 colors in palette, since they are often too light to show up on background
    elif palette_type == 'diverging':
        palette_colors = getattr(plotly.colors.diverging, palette)
        if palette == 'RdYlBu':  # Chaning middle color since default is too light to see
            # It was requested that the midpoint color for the divinging palette "RdYlBl" be changed to a darker yellow
            mid_index = len(palette_colors) // 2
            palette_colors[mid_index] = '#DAA520'
    else:
        raise ValueError(f"Palette type '{palette_type}' is not recognized")
    # Calculate evenly spaced indices
    indices = [int(i * (len(palette_colors) - 1) / (num_colors - 1)) for i in range(num_colors)]
    return ['rgba(0, 0, 0, 0.62)'] + [palette_colors[i] for i in indices]

# Setup color mapping for sample points
color_mapping = {
    'pH': {
        'ranges': [0, 6.4, 8.5],
        'ranges_descr': ['No Data', '0-6.4 Acidic', '6.5-8.5 Normal', '8.6-14 Basic'],
        'colors': 'RdYlBu',
        'palette': 'diverging'
    },
    'DO(mg/L)': {
        'ranges': [0, 5, 6],
        'ranges_descr': ['No Data', '0-5 Very low', '5-6 Low', '>6 Ideal'],
        'colors': 'RdYlBu',
        'palette': 'diverging'
    },
    'Conductivity(us/cm)': {
        'ranges': [0, 200, 400, 600, 800],
        'ranges_descr': ['No Data', '0-200', '200-400', '400-600', '600-800', '>800'],
        'colors': 'Blues',
        'palette': 'sequential'
    },
    'Phosphorus': {
        'ranges': [0, 0.04, 0.06, 0.1, 0.15],
        'ranges_descr': ['No Data', '<0.04 Very low', '0.04-0.06 Low', '0.06-0.1 Moderate', '0.1-0.15 High', '>0.15 Very high'],
        'colors': 'YlOrRd',
        'palette': 'sequential'
    },
    'Ecoli (MPN/100mL)': {
        'ranges': [0, 100, 300, 1000, 2419],
        'ranges_descr': ['No Data', '0-100 Low', '100-300 Elevated', '300-1000 High', '1000 - 2419 Very High', '>2419 Too High to Measure'],
        'colors': 'Reds',
        'palette': 'sequential'
    },
    'D.O%': {
        'ranges': [0, 80, 100],
        'ranges_descr': ['No Data', '0-80 Very low', '80-100 Low', '>100 Ideal'],
        'colors': 'RdYlBu',
        'palette': 'diverging'
    },
    'TEMP': {
        'ranges': [0, 11, 13, 15],
        'ranges_descr': ['No Data', '0-11', '11-13', '13-15', '>15'],
        'colors': 'PuBu',
        'palette': 'sequential'
    },
    'Enterococcus': {
        'ranges': [0, 300, 400, 500],
        'ranges_descr': ['No Data', '0-300', '300-400', '400-500', 'Enterococcus > 500'],
        'colors': 'BuPu',
        'palette': 'sequential'
    },
    'HF183 (MPN/100mL)': {
        'ranges': [0, 15, 20, 25],
        'ranges_descr': ['No Data', '0-15 Below Detection Limit', '15-20 Low', '20-25 High', '>25 Very High'],
        'colors': 'PuRd',
        'palette': 'sequential'
    }
}

# Update the dictionary with list of colors from the selected color brewer palette
for param, mapping in color_mapping.items():
    num_colors = len(mapping['ranges']) + 1
    mapping['colors'] = get_even_colors(mapping['colors'], mapping['palette'], num_colors)
    # print(param, ':', mapping['colors'])

def map_colors(param, value):
    if param not in color_mapping:
        return 'black'  # Default color if param is not found

    # Get the ranges and colors for the given param
    ranges = color_mapping[param]['ranges']
    colors = color_mapping[param]['colors']

    # Use bisect to find the index of the range
    index = bisect.bisect_left(ranges, value)

    # Return the corresponding color
    return colors[index]

# Update the Color Ranges Key with colors
for param, mapping in color_mapping.items():
    ranges_descr = mapping['ranges_descr']
    colors = mapping['colors']

    # Initialize an empty list to store the tuples
    color_ranges[param] = []

    # Iterate through the indices of the colors and descriptions
    for i in range(len(colors)):
        color = colors[i]
        description = ranges_descr[i]
        # Append the tuple to the list
        color_ranges[param].append((color, description))

@app.callback(
    [Output('site-info-display', 'children'),
     Output('date-image-list', 'children'),
     Output('debug-output', 'children')],
    [Input('map', 'clickData')]
)
def show_site_image_on_click(click):
    if not click:
        return 'Click on a site on the map to display data.', '', ''
    point = click['points'][0]
    if 'customdata' in point and point['customdata']:
        site_name = point['customdata'][0]  # Get SiteName from the customdata

        # Collect all image paths for the site
        image_dir = 'assets/'
        all_images = [img for img in os.listdir(image_dir) if f"site_image_{site_name}_" in img]


        # Group images by date
        images_by_date = {}
        for img_path in all_images:
            try:
                parts = img_path.split('_')
                if len(parts) >= 4:
                    date_str = parts[3]
                    img_date = datetime.strptime(date_str, '%Y-%m-%d').date()

                    if img_date not in images_by_date:
                        images_by_date[img_date] = []
                    images_by_date[img_date].append(img_path)
                else:
                    raise ValueError(f"Invalid filename pattern: {img_path}")
            except Exception as e:
                print(f"Error parsing date for image: {img_path}. Error: {e}")

        sorted_dates = sorted(images_by_date.keys(), reverse=True)

        # Generate the children for the images
        children = []
        for img_date in sorted_dates:
            date_section = [html.H4(f"Date: {img_date}", style={'font-family': 'Helvetica, sans-serif'})]
            date_section += [
                html.Img(src=f"/assets/{img}", style={'width': '95%', 'margin-bottom': '4px', 'object-fit': 'contain'})
                for img in images_by_date[img_date]
            ]
            children.append(html.Div(date_section, style={'margin-bottom': '0px'}))
        children.append(html.Div('', style={'margin-bottom': '0px'}))

        return f"Sample Site: {site_name}", children, ''

    return 'Click on a site on the map to display data.', '', ''

# Callback to update the map when the slider value changes
@app.callback(
    [Output('map', 'figure'),
    Output('lat-lon', 'data'),
    Output('zoom-level', 'data')],
    [Input('date-slider', 'value'),
    #  Input('encampment-toggle', 'value'),
     Input('color-dropdown', 'value'),
     Input('map', 'relayoutData')],
     [State('lat-lon', 'data'),
     State('zoom-level', 'data')]
)
def update_map(selected_date_index, color_value, relayout_data, lat_lon, current_zoom):
    fig = go.Figure()

    # Check which input triggered the callback
    ctx = callback_context

    if ctx.triggered:
        triggered_input = ctx.triggered[0]['prop_id'].split('.')[0]
        # Log the triggered input to a file
        message = f"Callback triggered by: {triggered_input}"


    # Get the current latitude and longitude from the stored data
    current_lat = lat_lon['lat']
    current_lon = lat_lon['lon']
    zoom_level = current_zoom

    # Use the new center and zoom level from relayoutData if it exists
    if relayout_data:
        new_zoom = relayout_data.get('mapbox.zoom', current_zoom)

        if 'mapbox.center' in relayout_data and triggered_input == 'map':
            new_lat = relayout_data['mapbox.center']['lat']
            new_lon = relayout_data['mapbox.center']['lon']
            return dash.no_update, {'lat': new_lat, 'lon': new_lon}, zoom_level

        # Zoom change detected: proceed with map update
        if new_zoom != current_zoom:
            zoom_level = new_zoom

    # Calculate the shift value based on the zoom level
    # shift_value = calculate_latitude_shift(zoom_level)
    shift_value = 0.00182

    selected_date = unique_dates[selected_date_index]  # Get the selected date using the index

    included_samples = merged[merged['date'] <= selected_date]

    # Preprocess the DataFrame to create a custom hover text column
    no_data_indicator = 'No Data'
    included_samples['hover_text'] = included_samples.apply(lambda row: (
        f"<b>Sample Site: {row['SampleSite']}</b><br>"
        f"Date: {row['date'].strftime('%Y-%b-%d')}</b><br>"
        f"pH: {row['pH'] if row['pH'] != -1 else no_data_indicator}<br>"
        f"TEMP: {row['TEMP'] if row['TEMP'] != -1 else no_data_indicator}<br>"
        f"DO(mg/L): {row['DO(mg/L)'] if row['DO(mg/L)'] != -1 else no_data_indicator}<br>"
        f"Conductivity(us/cm): {row['Conductivity(us/cm)'] if row['Conductivity(us/cm)'] != -1 else no_data_indicator}<br>"
        f"Phosphorus: {row['Phosphorus'] if row['Phosphorus'] != -1 else no_data_indicator}<br>"
        f"Ecoli (MPN/100mL): {row['Ecoli (MPN/100mL)'] if row['Ecoli (MPN/100mL)'] != -1 else no_data_indicator}<br>"
        f"Enterococcus: {row['Enterococcus'] if row['Enterococcus'] != -1 else no_data_indicator}<br>"
        f"HF183 (MPN/100mL): {row['HF183 (MPN/100mL)'] if row['HF183 (MPN/100mL)'] != -1 else no_data_indicator}<br>"),                                                    
    axis=1)

    included_encampments = merged_encampments[merged_encampments['date'] <= selected_date]

    if not included_samples.empty:
        last_sample_date = included_samples['date'].max()
        included_samples = included_samples[included_samples['date'] == last_sample_date]

    if not included_encampments.empty:
        last_encampment_date = included_encampments['date'].max()
        included_encampments = included_encampments[included_encampments['date'] == last_encampment_date]

    descriptions = encampments['HomelessnessScore'].map(description_dict)
    colors = included_encampments['HomelessnessScore'].map(color_dict)
    included_encampments['color'] = colors

    if color_value in included_samples.columns:
        included_samples['color'] = included_samples[color_value].apply(lambda value: map_colors(color_value, value))
    else:
        included_samples['color'] = 'blue'  # default color if color_value is not a valid column

    if color_value in included_encampments.columns and color_value != 'HomelessnessScore':
        included_encampments['color'] = included_encampments[color_value].apply(lambda value: map_colors(color_value, value))
    elif 'HomelessnessScore' in included_encampments.columns:
        included_encampments['color'] = included_encampments['HomelessnessScore'].map(color_dict)
    else:
        included_encampments['color'] = 'red'  # default color if color_value is not a valid column

    # Draw Santa Rosa Creek on map
    # Initialize list for LineString traces
    lines = []

    # Extract coordinates for LineStrings
    for geom in srcreek_gdf.geometry:
        if geom.geom_type == 'LineString' and not geom.is_empty:
            x, y = geom.xy
            # Ensure x and y are lists of longitudes and latitudes
            lon = list(x)
            lat = list(y)

            # Append the LineString trace to the lines list
            lines.append(go.Scattermapbox(
                lon=lon,
                lat=lat,
                mode='lines',
                line=dict(width=2, color='rgba(102, 179, 255, 0.6)'),
                hoverinfo='none',
                name='Storm Drain Lines',
                showlegend=False
            ))
            # # Add LineStrings to the figure
    for line in lines:
        fig.add_trace(line)

    # Draw points for encampments
    # if 'SHOW' in encampment_toggle_value:
    included_encampments = included_encampments[included_encampments['HomelessnessScore'] == 1]
    fig.add_trace(go.Scattermapbox(
        lat=included_encampments['Latitude'],
        lon=included_encampments['Longitude'],
        mode='markers',
        marker=dict(symbol="campsite", color=included_encampments['color'], size=10),
        text=included_encampments.apply(lambda
                                            row: f"Encampment Site: {row['EncampmentSite']}<br>Notes: {row['Notes'] if pd.notna(row['Notes']) else 'None'}",
                                        axis=1),
        hoverinfo='text',
        # custom_data=included_encampments[['EncampmentSite','date']],
        name="Encampments",
        showlegend=False
    ))

    # Draw lines from original points to shifted points (Water Sample Data)
    for index, row in included_samples.iterrows():
        orig_lat = row['Latitude']
        orig_lon = row['Longitude']
        shifted_lat = orig_lat + shift_value
        shifted_lon = orig_lon

        fig.add_trace(go.Scattermapbox(
            lat=[orig_lat, shifted_lat],
            lon=[orig_lon, shifted_lon],
            mode='lines',
            line=dict(width=2, color='rgba(0, 0, 0, .5)'),
            hoverinfo='skip',
            text='',
            name='',
            showlegend=False
        ))

    # Draw points for Water Sample Data
    fig.add_trace(go.Scattermapbox(
      lat=included_samples['Latitude'] + shift_value,
      lon=included_samples['Longitude'],
      mode='markers',
      marker=dict(
          symbol="circle",
          color=included_samples['color'],
          size=12,
          opacity=.8,
          sizemode='area'
      ),
      customdata=included_samples[['SampleSite', 'date', 'pH', 'TEMP', 'DO(mg/L)', 'Conductivity(us/cm)', 'Phosphorus', 'Ecoli (MPN/100mL)', 'Enterococcus', 'HF183 (MPN/100mL)']],
      text=included_samples['hover_text'],
      name="",
      showlegend=False
    ))

    fig.update_layout(
        mapbox_style="light",
        mapbox_layers=[],
        mapbox=dict(center=dict(lat=current_lat, lon=current_lon),
                    zoom=zoom_level,
                    accesstoken=os.getenv('MAPBOX_TOKEN')
                    ),
        margin={"r": 0, "t": 0, "l": 0, "b": 0}
    )

    return fig, lat_lon, zoom_level


app.run_server(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 8080)))
