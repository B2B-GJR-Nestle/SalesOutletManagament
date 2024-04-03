import streamlit as st
import pandas as pd
import folium
from geopy.distance import geodesic
import requests
from polyline import decode
from PIL import Image
import threading

img = Image.open('Nestle_Logo.png')
st.set_page_config(page_title="Salesman Outlet Management Tool", page_icon=img)

# Function to calculate distance using geodesic distance (haversine formula)
def calculate_distance(origin, destination):
    return geodesic(origin, destination).kilometers

# Function to make API requests concurrently
def make_api_requests(base_url, origins, destinations):
    responses = []

    # Function to make a single API request
    def make_request(origin, destination):
        response = requests.get(base_url + f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}")
        responses.append(response.json())

    # Create threads for each API request
    threads = []
    for origin, destination in zip(origins, destinations):
        thread = threading.Thread(target=make_request, args=(origin, destination))
        threads.append(thread)
        thread.start()

    # Wait for all threads to finish
    for thread in threads:
        thread.join()

    return responses

# Function to generate scheduling with balanced visit orders across days
def generate_scheduling(df, office_coord):
    # Sort dataframe by 'NAMA SALESMAN', 'DAY', and 'NAMA TOKO' columns
    df = df.sort_values(by=['NAMA SALESMAN', 'DAY', 'NAMA TOKO'])

    # Get unique office location
    office_location = office_coord

    # Create a dictionary to store visit orders and distances
    visit_orders = {}

    # Generate visit orders for each salesman
    for salesman, group in df.groupby(['NAMA SALESMAN', 'DAY']):
        visit_orders[salesman] = {}

        # Get unique days for the current salesman
        unique_days = group['DAY'].unique()

        # Generate visit orders for each unique day
        for day in unique_days:
            visit_orders[salesman][day] = {}

            # Filter outlets for the current day
            day_group = group[group['DAY'] == day]
            outlets = day_group['NAMA TOKO'].tolist()  # Get outlets for the current day

            # Initialize variables to keep track of previous outlet
            prev_outlet = None

            # Continue generating visit orders until all outlets for the day are visited
            visit_order = 1
            while outlets:
                # Find nearest outlet from the previous outlet and make it visit order 1
                outlet_distances = {}
                for outlet in outlets:
                    outlet_location = (day_group[day_group['NAMA TOKO'] == outlet]['Latitude'].iloc[0], 
                                        day_group[day_group['NAMA TOKO'] == outlet]['Longitude'].iloc[0])
                    if prev_outlet is not None:
                        distance = calculate_distance(prev_outlet, outlet_location)
                        outlet_distances[outlet] = distance
                    else:
                        # If it's the first outlet, calculate distance from office
                        distance = calculate_distance(office_location, outlet_location)
                        outlet_distances[outlet] = distance

                nearest_outlet = min(outlet_distances, key=outlet_distances.get)
                visit_orders[salesman][day][visit_order] = {'NAMA TOKO': nearest_outlet, 
                                                             'Distance': outlet_distances[nearest_outlet],
                                                             'Coordinates': outlet_location}

                # Remove the nearest outlet from the list of outlets
                outlets.remove(nearest_outlet)

                # Update previous outlet
                prev_outlet = outlet_location

                # Increment visit order
                visit_order += 1

    # Convert visit orders dictionary into a DataFrame
    scheduling_data = []
    for salesman, days_data in visit_orders.items():
        for day, visit_orders in days_data.items():
            for visit_order, data in visit_orders.items():
                scheduling_data.append([salesman[0], day, visit_order, data['NAMA TOKO'], data['Distance'], data['Coordinates']])

    scheduling_df = pd.DataFrame(scheduling_data, columns=['NAMA SALESMAN', 'Day', 'Visit Order', 'NAMA TOKO', 'Distance', 'Coordinates'])

    # Merge scheduling_df with longitude and latitude columns
    scheduling_df = pd.merge(scheduling_df, df[['NAMA TOKO', 'Latitude', 'Longitude', 'KUNJUNGAN']], on='NAMA TOKO')

    return scheduling_df

# Function to filter scheduling DataFrame by salesman, day, and visit type
def filter_schedule(scheduling_df, selected_salesman, selected_day, selected_visit_type):
    filtered_schedule = scheduling_df[(scheduling_df['NAMA SALESMAN'] == selected_salesman) & 
                                      (scheduling_df['Day'] == selected_day) &
                                      (scheduling_df['KUNJUNGAN'] == selected_visit_type)]
    return filtered_schedule

# Function to generate Folium map
# Function to get route polyline using OSRM API
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
            outlet_name = row['NAMA TOKO']
            outlet_lat = row['Latitude']
            outlet_lon = row['Longitude']
            day = row['Day']
            visit_order = row['Visit Order']

            # Assign color for marker and polyline based on day
            marker_color = day_colors.get(day, 'black')

            # Add marker for outlet
            popup_message = f"{outlet_name} \n Day: {day}"
            folium.Marker(location=[outlet_lat, outlet_lon], popup=popup_message, icon=folium.Icon(color=marker_color)).add_to(m)

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
            outlet_name = row['NAMA TOKO']
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

# Limit visit per day
default_num = 25
limit = st.number_input("Enter number of Store to Visit in A Day:",value=default_num, step=1)

if uploaded_file is not None:
    # Read uploaded file
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        df.dropna(subset=['Latitude'], inplace=True)
        st.sidebar.write("Data Preview:")
        st.sidebar.write(df.head())

        # Generate scheduling
        office_latitude = -6.558031
        office_longitude = 106.691809
        office_coord = (office_latitude,office_longitude)
        scheduling_df = generate_scheduling(df,office_coord)

        # Filter by salesman
        salesmen = scheduling_df['NAMA SALESMAN'].unique()
        selected_salesman = st.sidebar.selectbox("Select salesman:", salesmen)

        # Filter by day
        days = scheduling_df['Day'].unique()
        selected_day = st.sidebar.selectbox("Select day:", days)

        # Filter by visit type
        visit_types = scheduling_df['KUNJUNGAN'].unique()
        selected_visit_type = st.sidebar.selectbox("Select visit type:", visit_types)

        # Filter scheduling by salesman, day, and visit type
        filtered_schedule = filter_schedule(scheduling_df, selected_salesman, selected_day, selected_visit_type)

        # Display filtered scheduling
        st.write("Generated Scheduling for", selected_salesman, "on", selected_day)
        st.write(filtered_schedule)

        # Display Folium map if schedule is not empty
        if not filtered_schedule.empty:
            st.markdown(f'<span style="font-size:16px;">📍 Map showing connections for {selected_salesman} on {selected_day} that need to visit {filtered_schedule["Distance"].count()} outlet(s) around <b>{round(filtered_schedule["Distance"].sum(),3)} km<b></span>', unsafe_allow_html=True)
            folium_map_html = generate_folium_map(df, filtered_schedule, office_latitude, office_longitude)
            st.components.v1.html(folium_map_html, width=825, height=550)
        else:
            st.write(f"{selected_salesman} Has No Visit Schedule on {selected_day}")

    except Exception as e:
        st.write("An error occurred:", e)

st.sidebar.image("Nestle_Signature.png")
st.sidebar.write("""<p style='font-size: 14px;'>This Web-App is designed to facilitate HOA or Distributor to generate alternative scheduling for salesman journey plan made by <b>Nestlé Management Trainee 2023<b></p>""", unsafe_allow_html=True)
st.sidebar.write("""<p style='font-size: 13px;'>For any inquiries, error handling, or assistance, please feel free to reach us through Email: <br>
<a href="mailto:Ananda.Cahyo@id.nestle.com">Ananda.Cahyo@id.nestle.com <br>
<a href="mailto:Kemal.Ardaffa@id.nestle.com">Kemal.Ardaffa@id.nestle.com <br>
<a href="mailto:Farah.Risha@id.nestle.com">Farah.Risha@id.nestle.com</a></p>""", unsafe_allow_html=True)
