import os
import pandas as pd
import streamlit as st
import folium
from folium.plugins import MarkerCluster
from sklearn.cluster import KMeans
from PIL import Image

img = Image.open('Nestle_Logo.png')
st.set_page_config(page_title="Salesman Outlet Management Tool", page_icon=img)

def load_data():
    # Load or initialize your dataframe here
    return pd.DataFrame()

def main():
    st.title("🌏Outlet Management Tools")
    
    # Load data
    df = load_data()

    # Initialize session state
    if 'new_outlets' not in st.session_state:
        st.session_state.new_outlets = []

    # Step 1: Allow users to upload a sales database file (Excel or CSV format)
    uploaded_file = st.file_uploader("Upload Sales Database (Excel or CSV)", type=["xlsx", "csv"])

    if uploaded_file is not None:
        if uploaded_file.name.endswith('.xlsx'):
            new_data = pd.read_excel(uploaded_file)
        else:
            new_data = pd.read_csv(uploaded_file)

        # Concatenate the new data with existing dataframe
        df = pd.concat([df, new_data], ignore_index=True)

    # Step 2: Cluster the initial outlets and calculate centroids
    if st.session_state.new_outlets:
        new_outlets_df = pd.DataFrame(st.session_state.new_outlets)
        df = pd.concat([df, new_outlets_df], ignore_index=True)

    # Continue with your clustering logic only if the dataframe is not empty
    if not df.empty:
        # Continue with your clustering logic
        unique_salesmen = df['Salesman'].unique()
        colors = ['blue', 'green', 'red', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen']
        salesman_mapping = {salesman: colors[i % len(colors)] for i, salesman in enumerate(unique_salesmen)}

        if len(df['Salesman']) < 5*len(unique_salesmen):
            cluster_sales = len(unique_salesmen)
        else:
            cluster_sales = 3*len(unique_salesmen)
        kmeans_model = KMeans(n_clusters=cluster_sales, random_state=42).fit(df[['Latitude', 'Longitude']])
        initial_kmeans_labels = kmeans_model.predict(df[['Latitude', 'Longitude']])
        initial_centroids = kmeans_model.cluster_centers_

        initial_centroid_salesman = {tuple(centroid): salesman for centroid, salesman in zip(initial_centroids, unique_salesmen)}

        # GeoJSON file path for KECAMATAN borders
        bekasi_geojson_path = "kabkot_bekasi.geojson"

        center_lat = df['Latitude'].mean()
        center_lon = df['Longitude'].mean()
        m = folium.Map(location=[center_lat, center_lon], zoom_start=10)

        # Load GeoJSON data
        bekasi_geojson = folium.GeoJson(bekasi_geojson_path)

        # Create a dictionary to store GeoJSON layers for each KECAMATAN
        kecamatan_layers = {}

        for feature in bekasi_geojson.data['features']:
            kecamatan = feature['properties']['KECAMATAN']
            if kecamatan not in kecamatan_layers:
                kecamatan_layers[kecamatan] = folium.GeoJson(
                    {
                        "type": "FeatureCollection",
                        "features": [feature]
                    },
                    name=f'Kecamatan - {kecamatan}',
                    style_function=lambda feature: {
                        'fillColor': 'white',
                        'color': 'navy',
                        'weight': 1.5
                    },
                    tooltip=folium.GeoJsonTooltip(fields=['KECAMATAN', 'Shape_Area'],
                                                   aliases=['Kecamatan', 'Area'],
                                                   labels=True,
                                                   sticky=True)
                ).add_to(m)

        marker_cluster = MarkerCluster().add_to(m)

        # Create a dictionary to store the salesman color
        salesman_color_dict = {salesman: color for salesman, color in salesman_mapping.items()}
        default_color = 'gray'  # Assign a default color for outlets without a specified salesman

        # Create a dictionary to store the most appearing salesman for each center coordinate
        center_salesman = {}

        # Iterate through the outlets and calculate the most appearing salesman for each center coordinate
        for i, row in df.iterrows():
            center_coords = tuple(initial_centroids[initial_kmeans_labels[i]])  # Convert NumPy array to tuple
            salesman_name = row['Salesman']
            if center_coords not in center_salesman:
                center_salesman[center_coords] = {}
            center_salesman[center_coords][salesman_name] = center_salesman[center_coords].get(salesman_name, 0) + 1

        # Assign the most appearing salesman for each center coordinate
        for centroid, salesmen_count in center_salesman.items():
            most_appearing_salesman = max(salesmen_count, key=salesmen_count.get)
            initial_centroid_salesman[centroid] = most_appearing_salesman

        # Plot the markers, polylines, and assign salesman for center coordinates
        for i, row in df.iterrows():
            salesman_name = row['Salesman']
            salesman_color = salesman_color_dict.get(salesman_name, default_color)  # Use default color for missing salesman
            popup_text = f"{row['Outlet']} - {salesman_name}"
            folium.Marker(
                location=[row['Latitude'], row['Longitude']],
                popup=popup_text,
                icon=folium.Icon(color=salesman_color)
            ).add_to(marker_cluster)

        for centroid, salesman in initial_centroid_salesman.items():
            color = salesman_mapping[salesman]
            folium.Marker(
                location=centroid,
                popup=f"Salesman - {salesman} - {unique_salesmen.tolist().index(salesman)}",
                icon=folium.Icon(color=color)
            ).add_to(m)

        for i, row in df.iterrows():
            outlet_coords = [row['Latitude'], row['Longitude']]
            salesman_center_coords = initial_centroids[initial_kmeans_labels[i]]
            salesman_color = salesman_color_dict.get(row['Salesman'], default_color)  # Use default color for missing salesman
            folium.PolyLine([outlet_coords, salesman_center_coords], color=salesman_color, weight=3, opacity=0.5).add_to(m)

        # Add layer control for KECAMATAN layers
        folium.LayerControl().add_to(m)

        # Display the map
        st.markdown(f"## Salesman Coverage Map")
        st.components.v1.html(m._repr_html_(), width=700, height=500)

        # Step 3: Accept new longitude, latitude, and outlet information from the user
        st.sidebar.markdown("## Add New Outlet")
        new_outlet_name = st.sidebar.text_input("Enter the name of the outlet:")
        new_outlet_longitude = st.sidebar.number_input("Enter the longitude of the outlet:", format="%.4f")
        new_outlet_latitude = st.sidebar.number_input("Enter the latitude of the outlet:", format="%.4f")

        if st.sidebar.button("Add Outlet"):
            new_outlet = {'Outlet': new_outlet_name, 'Longitude': new_outlet_longitude, 'Latitude': new_outlet_latitude}

            # Determine the suggested salesman for the new outlet based on proximity
            nearest_salesman_idx = kmeans_model.predict([[new_outlet_latitude, new_outlet_longitude]])[0]
            suggested_salesman = initial_centroid_salesman[tuple(kmeans_model.cluster_centers_[nearest_salesman_idx])]
            new_outlet['Salesman'] = suggested_salesman

            st.session_state.new_outlets.append(new_outlet)

            # Refresh the page to update the map with the new outlet
            st.experimental_rerun()

    else:
        st.warning("Please upload a sales database file.")

    # Display the combined dataframe
    st.sidebar.markdown("## Outlets Data")
    st.sidebar.write(df)

    st.sidebar.image("Nestle_Signature.png")
    st.sidebar.write("""<p style='font-size: 14px;'>This Web-App is designed to facilitate HOA or Distributor in mapping salesman coverage of outlets for PT Nestlé Indonesia Customer made by <b>Nestlé Management Trainee 2023<b></p>""", unsafe_allow_html=True)
    st.sidebar.write("""<p style='font-size: 13px;'>For any inquiries, error handling, or assistance, please feel free to reach us through Email: <a href="mailto:Ananda.Cahyo@id.nestle.com">Ananda.Cahyo@id.nestle.com</a></p>""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
