import streamlit as st
import pandas as pd
import folium
import numpy as np

st.set_page_config(page_title="Salesman Outlet Management Tool", page_icon="🚶‍♂️")

# Function to calculate distance using Haversine formula
def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    r = 6371  # Radius of earth in kilometers. Use 3956 for miles
    return c * r

# Function to generate scheduling
def generate_scheduling(df):
    # Sort dataframe by 'Salesman' and 'Outlet' columns
    df = df.sort_values(by=['Salesman', 'Outlet'])

    # Get unique office location
    office_lat, office_lon = df.iloc[0]['Latitude'], df.iloc[0]['Longitude']

    # Create a dictionary to store visit orders and distances
    visit_orders = {}

    # Generate visit orders for each salesman
    for salesman, group in df.groupby('Salesman'):
        visit_orders[salesman] = {}
        day_counter = 0
        visit_order = 1

        for _, row in group.iterrows():
            outlet = row['Outlet']
            outlet_lat, outlet_lon = row['Latitude'], row['Longitude']
            distance = haversine(office_lon, office_lat, outlet_lon, outlet_lat)

            if day_counter >= 5:  # If already visited five outlets, move to the next day
                day_counter = 0
                visit_order += 1
            day = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'][day_counter]
            if day not in visit_orders[salesman]:
                visit_orders[salesman][day] = {}
            visit_orders[salesman][day][visit_order] = {'Outlet': outlet, 'Distance': distance, 'Coordinates': (outlet_lat, outlet_lon)}
            day_counter += 1

    # Generate scheduling DataFrame
    scheduling_data = []
    for salesman, days in visit_orders.items():
        for day, visit_orders in days.items():
            for visit_order, data in visit_orders.items():
                scheduling_data.append([salesman, day, visit_order, data['Outlet'], data['Distance'], data['Coordinates']])
    scheduling_df = pd.DataFrame(scheduling_data, columns=['Salesman', 'Day', 'Visit Order', 'Outlet', 'Distance', 'Coordinates'])

    # Merge scheduling_df with longitude and latitude columns
    scheduling_df = pd.merge(scheduling_df, df[['Outlet', 'Latitude', 'Longitude']], on='Outlet')

    return scheduling_df

# Function to filter scheduling DataFrame by salesman
def filter_schedule(scheduling_df, salesman):
    return scheduling_df[scheduling_df['Salesman'] == salesman]

import random

# Function to generate Folium map
def generate_folium_map(df, filtered_schedule, office_latitude, office_longitude, map_width=800, map_height=600):
    m = folium.Map(location=[office_latitude, office_longitude], zoom_start=10)

    # Add marker for the office with emoji
    folium.Marker(
        location=[office_latitude, office_longitude],
        popup="Office",
        icon=folium.Icon(color='green', icon='briefcase', prefix='fa')
    ).add_to(m)

    # Define colors for different days
    day_colors = {'Monday': 'blue', 'Tuesday': 'green', 'Wednesday': 'red', 'Thursday': 'orange', 'Friday': 'purple'}

    # Initialize variables to track previous outlet's day and visit order
    prev_outlet_day = None
    prev_outlet_visit_order = None
    prev_outlet_location = None

    # Add markers and connect with polyline
    if not filtered_schedule.empty:
        for _, row in filtered_schedule.iterrows():
            outlet_name = row['Outlet']
            outlet_lat = row['Latitude']
            outlet_lon = row['Longitude']
            day = row['Day']
            visit_order = row['Visit Order']

            # Assign color for marker and polyline based on day
            marker_color = day_colors.get(day, 'black')

            # Add marker for outlet
            popup_message = f"{outlet_name} - Visit Order: {visit_order} - Day: {day}"
            folium.Marker(location=[outlet_lat, outlet_lon], popup=popup_message, icon=folium.Icon(color=marker_color)).add_to(m)

            # Connect to previous outlet if in the same day and consecutive visit order
            if prev_outlet_day == day and prev_outlet_visit_order == visit_order - 1:
                locations = [prev_outlet_location, (outlet_lat, outlet_lon)]
                polyline_color = day_colors.get(day, 'black')
                folium.PolyLine(locations=locations, color=polyline_color).add_to(m)

            # Connect outlet with Visit Order 1 to office
            if visit_order == 1:
                polyline_color = marker_color
                folium.PolyLine(locations=[(office_latitude, office_longitude), (outlet_lat, outlet_lon)], color=polyline_color).add_to(m)

            # Update variables for next iteration
            prev_outlet_day = day
            prev_outlet_visit_order = visit_order
            prev_outlet_location = (outlet_lat, outlet_lon)

    else:  # If no outlets are visited
        # Connect each standalone outlet to the office
        for _, row in df.iterrows():
            outlet_name = row['Outlet']
            outlet_lat = row['Latitude']
            outlet_lon = row['Longitude']
            popup_message = f"{outlet_name} - Standalone Outlet"
            folium.Marker(location=[outlet_lat, outlet_lon], popup=popup_message, icon=folium.Icon(color='gray')).add_to(m)
            folium.PolyLine(locations=[(office_latitude, office_longitude), (outlet_lat, outlet_lon)], color='gray').add_to(m)

    # Create HTML string for the map
    m_html = m._repr_html_()

    # Adjust map size using custom CSS
    m_html = f'<div style="width: {map_width}px; height: {map_height}px">{m_html}</div>'

    return m_html






# Streamlit UI
st.title('📅Salesman Scheduling Dashboard')

# Upload file
uploaded_file = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx"])

if uploaded_file is not None:
    # Read uploaded file
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        st.write("Data Preview:")
        st.write(df.head())

        # Generate scheduling
        scheduling_df = generate_scheduling(df)

        # Filter by salesman
        salesmen = scheduling_df['Salesman'].unique()
        selected_salesman = st.selectbox("Select salesman:", salesmen)
        filtered_schedule = filter_schedule(scheduling_df, selected_salesman)

        # Display filtered scheduling
        st.write("Generated Scheduling for", selected_salesman)
        st.write(filtered_schedule)

        # Display Folium map
        st.write("Map showing connections for", selected_salesman)
        office_latitude = -6.282723
        office_longitude = 106.989738
        folium_map_html = generate_folium_map(df, filtered_schedule, office_latitude, office_longitude)
        #folium_map_html = generate_folium_map(df, filtered_schedule)
        st.components.v1.html(folium_map_html,width=700, height=500)

    except Exception as e:
        st.write("An error occurred:", e)
