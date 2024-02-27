import os
import pandas as pd
import streamlit as st
import folium
from folium.plugins import MarkerCluster
from sklearn.cluster import KMeans, DBSCAN, OPTICS
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

        # Clustering with KMeans
        if st.checkbox("Show KMeans Map"):
            cluster_kmeans(df, unique_salesmen, salesman_mapping)

        # Clustering with DBSCAN
        if st.checkbox("Show DBSCAN Map"):
            cluster_dbscan(df, unique_salesmen, salesman_mapping)

        # Clustering with OPTICS
        if st.checkbox("Show OPTICS Map"):
            cluster_optics(df, unique_salesmen, salesman_mapping)

        # Step 3: Accept new longitude, latitude, and outlet information from the user
        st.sidebar.markdown("## Add New Outlet")
        new_outlet_name = st.sidebar.text_input("Enter the name of the outlet:")
        new_outlet_longitude = st.sidebar.number_input("Enter the longitude of the outlet:", format="%.4f")
        new_outlet_latitude = st.sidebar.number_input("Enter the latitude of the outlet:", format="%.4f")

        if st.sidebar.button("Add Outlet"):
            new_outlet = {'Outlet': new_outlet_name, 'Longitude': new_outlet_longitude, 'Latitude': new_outlet_latitude}

            # Determine the suggested salesman for the new outlet based on KMeans clustering
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


def cluster_kmeans(df, unique_salesmen, salesman_mapping):
    center_lat = df['Latitude'].mean()
    center_lon = df['Longitude'].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)

    # KMeans clustering
    kmeans_model = KMeans(n_clusters=len(unique_salesmen), random_state=42).fit(df[['Latitude', 'Longitude']])
    initial_kmeans_labels = kmeans_model.labels_
    initial_centroids = kmeans_model.cluster_centers_
    initial_centroid_salesman = {tuple(centroid): salesman for centroid, salesman in zip(initial_centroids, unique_salesmen)}

    # Plotting
    plot_map(df, m, initial_kmeans_labels, initial_centroid_salesman, salesman_mapping)


def cluster_dbscan(df, unique_salesmen, salesman_mapping):
    center_lat = df['Latitude'].mean()
    center_lon = df['Longitude'].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)

    # DBSCAN clustering
    dbscan_model = DBSCAN(eps=0.1, min_samples=5).fit(df[['Latitude', 'Longitude']])
    initial_dbscan_labels = dbscan_model.labels_
    unique_labels = set(initial_dbscan_labels)
    initial_centroids = {}
    center_salesman = {}
    for label in unique_labels:
        if label == -1:
            continue
        cluster_points = df[initial_dbscan_labels == label]
        cluster_center = cluster_points[['Latitude', 'Longitude']].mean()
        initial_centroids[label] = cluster_center.values
        center_salesman[label] = cluster_points['Salesman'].value_counts().idxmax()

    # Plotting
    plot_map(df, m, initial_dbscan_labels, center_salesman, salesman_mapping)


def cluster_optics(df, unique_salesmen, salesman_mapping):
    center_lat = df['Latitude'].mean()
    center_lon = df['Longitude'].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)

    # OPTICS clustering
    optics_model = OPTICS(min_samples=5).fit(df[['Latitude', 'Longitude']])
    initial_optics_labels = optics_model.labels_
    unique_labels = set(initial_optics_labels)
    initial_centroids = {}
    center_salesman = {}
    for label in unique_labels:
        if label == -1:
            continue
        cluster_points = df[initial_optics_labels == label]
        cluster_center = cluster_points[['Latitude', 'Longitude']].mean()
        initial_centroids[label] = cluster_center.values
        center_salesman[label] = cluster_points['Salesman'].value_counts().idxmax()

    # Plotting
    plot_map(df, m, initial_optics_labels, center_salesman, salesman_mapping)


def plot_map(df, m, labels, center_salesman, salesman_mapping):
    marker_cluster = MarkerCluster().add_to(m)
    salesman_color_dict = {salesman: color for salesman, color in salesman_mapping.items()}
    default_color = 'gray'

    for i, row in df.iterrows():
        salesman_name = row['Salesman']
        salesman_color = salesman_color_dict.get(salesman_name, default_color)
        popup_text = f"{row['Outlet']} - {salesman_name}"
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=popup_text,
            icon=folium.Icon(color=salesman_color)
        ).add_to(marker_cluster)

    for label, centroid in center_salesman.items():
        salesman = center_salesman[label]
        color = salesman_mapping[salesman]
        folium.Marker(
            location=centroid,
            popup=f"Salesman - {salesman}",
            icon=folium.Icon(color=color)
        ).add_to(m)

    for i, row in df.iterrows():
        outlet_coords = [row['Latitude'], row['Longitude']]
        cluster_center_coords = center_salesman[labels[i]]
        salesman_color = salesman_color_dict.get(row['Salesman'], default_color)
        folium.PolyLine([outlet_coords, cluster_center_coords], color=salesman_color, weight=3, opacity=0.5).add_to(m)

    folium.LayerControl().add_to(m)
    st.markdown(f"## Salesman Coverage Map")
    st.components.v1.html(m._repr_html_(), width=700, height=500)


if __name__ == "__main__":
    main()
