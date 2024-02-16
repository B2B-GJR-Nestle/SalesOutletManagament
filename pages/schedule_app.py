import streamlit as st
import pandas as pd
import folium
from geopy.distance import geodesic
import requests
from polyline import decode
from PIL import Image
from multiprocessing import Pool
from functools import partial

img = Image.open('Nestle_Logo.png')
st.set_page_config(page_title="Salesman Outlet Management Tool", page_icon=img)

#Limit visit per day
limit = 25

# Function to calculate distance using geodesic distance (haversine formula)
def calculate_distance(origin, destination):
    return geodesic(origin, destination).kilometers

def calculate_distances(origin, destination):
    base_url = "http://router.project-osrm.org/route/v1/driving/"
    params = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    response = requests.get(base_url + params)
    if response.status_code == 200:
        route_data = response.json()
        if 'routes' in route_data and len(route_data['routes']) > 0:
            return route_data['routes'][0]['distance'] / 1000  # Convert meters to kilometers
    return None

# Function to get route polyline from OSRM API
def get_route_polyline(origin, destination):
    base_url = "http://router.project-osrm.org/route/v1/driving/"
    params = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    response = requests.get(base_url + params)
    if response.status_code == 200:
        route_data = response.json()
        if 'routes' in route_data and len(route_data['routes']) > 0:
            polyline = route_data['routes'][0]['geometry']
            return decode(polyline)
    return []

# Function to generate scheduling with balanced visit orders across days
# Function to generate scheduling with balanced visit orders across days
def generate_scheduling(df):
    # Define the function to be executed in a separate process
    def generate_schedule(group):
        visit_orders = {}
        office_location = (group.iloc[0]['Latitude'], group.iloc[0]['Longitude'])

        # Initialize visit orders for each day
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']:
            visit_orders[day] = {}

        # Split outlets into days and find nearest outlet for each day
        outlets = group['Outlet'].tolist()
        num_outlets = len(outlets)
        day_counter = 0
        visit_order = 1

        while outlets:
            current_day = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][day_counter]

            # Take up to limit outlets for the current day
            outlets_today = outlets[:limit]
            outlets = outlets[limit:]

            # Calculate distances between office and outlets concurrently
            with Pool() as pool:
                partial_func = partial(calculate_distance, office_location, outlets_today, group)
                results = pool.map(partial_func, [outlets_today]*len(outlets_today))

            # Merge distances from all processes
            outlet_distances = {k: v for result in results for k, v in result.items()}

            # Find nearest outlet from office and make it visit order 1
            nearest_outlet = min(outlet_distances, key=outlet_distances.get)
            visit_orders[current_day][1] = {'Outlet': nearest_outlet, 'Distance': outlet_distances[nearest_outlet], 'Coordinates': (group[group['Outlet'] == nearest_outlet]['Latitude'].iloc[0], group[group['Outlet'] == nearest_outlet]['Longitude'].iloc[0])}

            # Remove the nearest outlet from the list of outlets
            outlets_today.remove(nearest_outlet)

            # Generate visit orders for the rest of the outlets
            visit_order = 1
            while outlets_today:
                if visit_order > limit:
                    visit_order = 1
                    day_counter += 1
                    if day_counter >= limit:
                        break

                last_assigned_outlet = visit_orders[current_day][visit_order]['Coordinates']
                nearest_outlet = None
                nearest_distance = float('inf')

                # Find the nearest outlet relative to the last assigned outlet
                for outlet in outlets_today:
                    outlet_location = (group[group['Outlet'] == outlet]['Latitude'].iloc[0], group[group['Outlet'] == outlet]['Longitude'].iloc[0])
                    distance = calculate_distance(last_assigned_outlet, outlet_location)
                    if distance < nearest_distance:
                        nearest_outlet = outlet
                        nearest_distance = distance

                # Assign the nearest outlet to the current day and visit order
                visit_orders[current_day][visit_order + 1] = {'Outlet': nearest_outlet, 'Distance': nearest_distance, 'Coordinates': (group[group['Outlet'] == nearest_outlet]['Latitude'].iloc[0], group[group['Outlet'] == nearest_outlet]['Longitude'].iloc[0])}
                outlets_today.remove(nearest_outlet)
                visit_order += 1

            day_counter += 1

        return visit_orders

    # Split dataframe by salesman and apply parallel processing
    visit_orders_list = []
    for _, group in df.groupby('Salesman'):
        visit_orders_list.append(generate_schedule(group))

    # Combine results into a single dictionary
    combined_visit_orders = {}
    for visit_orders in visit_orders_list:
        for day, orders in visit_orders.items():
            combined_visit_orders.setdefault(day, {}).update(orders)

    return combined_visit_orders
    
# Function to filter scheduling DataFrame by salesman
def filter_schedule(scheduling_df, salesman):
    return scheduling_df[scheduling_df['Salesman'] == salesman]

# Function to generate Folium map
# Function to create a text-based icon for the visit order number
def create_visit_order_icon(visit_order):
    return folium.DivIcon(html=f'<div style="font-size: 12pt; color: white; background-color: #645440; border-radius: 50%; '
                                f'width: 20px; height: 20px; line-height: 20px; text-align: center;">{visit_order}</div>')

# Function to generate Folium map
def generate_folium_map(df, filtered_schedule, office_latitude, office_longitude, map_width=800, map_height=600):
    m = folium.Map(location=[office_latitude, office_longitude], zoom_start=10)

    # Add marker for the office with emoji
    folium.Marker(
        location=[office_latitude, office_longitude],
        popup="PT. RMS BEKASI🏢",
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

            # Create icon with visit order number
            icon = create_visit_order_icon(visit_order)

            # Add marker for outlet
            popup_message = f"{outlet_name} \n Day: {day}"
            folium.Marker(location=[outlet_lat, outlet_lon], popup=popup_message, icon=icon).add_to(m)

            # Connect to previous outlet if in the same day and consecutive visit order
            if prev_outlet_day == day and prev_outlet_visit_order == visit_order - 1:
                # Get coordinates for the previous outlet
                prev_outlet_lat = prev_outlet_location[0]
                prev_outlet_lon = prev_outlet_location[1]
                
                # Get route polyline from the previous outlet to the current outlet
                locations = get_route_polyline((prev_outlet_lat, prev_outlet_lon), (outlet_lat, outlet_lon))
                
                # If route is available, add polyline to the map
                if locations:
                    polyline_color = day_colors.get(day, 'black')
                    folium.PolyLine(locations=locations, color=polyline_color).add_to(m)

            # Connect outlet with Visit Order 1 to office
            if visit_order == 1:
                polyline_color = marker_color
                # Get route polyline from office to outlet
                locations = get_route_polyline((office_latitude, office_longitude), (outlet_lat, outlet_lon))
                if locations:
                    folium.PolyLine(locations=locations, color=polyline_color).add_to(m)

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
        st.sidebar.write("Data Preview:")
        st.sidebar.write(df.head())

        # Generate scheduling
        scheduling_df = generate_scheduling(df)

        # Filter by salesman
        salesmen = scheduling_df['Salesman'].unique()
        selected_salesman = st.sidebar.selectbox("Select salesman:", salesmen)
        filtered_schedule = filter_schedule(scheduling_df, selected_salesman)

        # Filter by day
        days = scheduling_df['Day'].unique()
        selected_day = st.sidebar.selectbox("Select day:", days)
        filtered_schedule = filtered_schedule[filtered_schedule['Day'] == selected_day]

        # Display filtered scheduling
        st.write("Generated Scheduling for", selected_salesman, "on", selected_day)
        st.write(filtered_schedule)

        # Display Folium map if schedule is not empty
        if not filtered_schedule.empty:
            #st.write("📍 Map showing connections for", selected_salesman, "on", selected_day, "that need to visit",filtered_schedule['Distance'].count() ,"outlet(s) around", filtered_schedule['Distance'].sum(),"km")
            st.markdown(f'<span style="font-size:16px;">📍 Map showing connections for {selected_salesman} on {selected_day} that need to visit {filtered_schedule["Distance"].count()} outlet(s) around <b>{round(filtered_schedule["Distance"].sum(),3)} km<b></span>', unsafe_allow_html=True)
            office_latitude = -6.282723
            office_longitude = 106.989738
            folium_map_html = generate_folium_map(df, filtered_schedule, office_latitude, office_longitude)
            st.components.v1.html(folium_map_html, width=825, height=550)
        else:
            st.write(f"{selected_salesman} Has No Visit Schedule on {selected_day}")

    except Exception as e:
        st.write("An error occurred:", e)

st.sidebar.image("Nestle_Signature.png")
st.sidebar.write("""<p style='font-size: 14px;'>This Web-App is designed to facilitate HOA or Distributor to generate alternative scheduling for salesman journey plan made by <b>Nestlé Management Trainee 2023<b></p>""", unsafe_allow_html=True)
st.sidebar.write("""<p style='font-size: 13px;'>For any inquiries, error handling, or assistance, please feel free to reach us through Email: <a href="mailto:Ananda.Cahyo@id.nestle.com">Ananda.Cahyo@id.nestle.com</a></p>""", unsafe_allow_html=True)

