import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import json
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------
st.set_page_config(
    page_title="SOTA USA County Explorer",
    layout="wide",
)

st.title("🇺🇸 SOTA USA County Explorer")
st.caption("Explore US SOTA summits and the counties they fall within")

# ---------------------------------------------------
# STATE FIPS → ABBREVIATION MAP
# ---------------------------------------------------
STATE_FIPS = {
    "01": "AL","02": "AK","04": "AZ","05": "AR","06": "CA","08": "CO",
    "09": "CT","10": "DE","11": "DC","12": "FL","13": "GA","15": "HI",
    "16": "ID","17": "IL","18": "IN","19": "IA","20": "KS","21": "KY",
    "22": "LA","23": "ME","24": "MD","25": "MA","26": "MI","27": "MN",
    "28": "MS","29": "MO","30": "MT","31": "NE","32": "NV","33": "NH",
    "34": "NJ","35": "NM","36": "NY","37": "NC","38": "ND","39": "OH",
    "40": "OK","41": "OR","42": "PA","44": "RI","45": "SC","46": "SD",
    "47": "TN","48": "TX","49": "UT","50": "VT","51": "VA","53": "WA",
    "54": "WV","55": "WI","56": "WY"
}

# ---------------------------------------------------
# LOAD DATA
# ---------------------------------------------------
@st.cache_data
def load_summits():
    df = pd.read_csv("w-summits.csv")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df = df.dropna(subset=["Longitude", "Latitude"])
    return df

@st.cache_resource
def load_counties():
    with open("counties.json", "r", encoding="latin1") as f:
        data = json.load(f)
    counties = gpd.GeoDataFrame.from_features(data["features"])
    counties.set_crs("EPSG:4326", inplace=True)
    return counties

@st.cache_resource
def spatial_join(summits_df, _counties_gdf):
    geometry = [Point(xy) for xy in zip(summits_df["Longitude"], summits_df["Latitude"])]
    summits_gdf = gpd.GeoDataFrame(summits_df, geometry=geometry, crs="EPSG:4326")
    joined = gpd.sjoin(summits_gdf, _counties_gdf, how="left", predicate="intersects")
    joined["StateAbbr"] = joined["STATE"].map(STATE_FIPS)
    joined["CountyFull"] = joined["NAME"] + " County, " + joined["StateAbbr"]
    grouped = (
        joined.groupby("SummitCode")
        .agg({
            "SummitName": "first",
            "RegionName": "first",
            "AssociationName": "first",
            "Latitude": "first",
            "Longitude": "first",
            "CountyFull": lambda x: ", ".join(sorted(set(x.dropna()))),
            "Points": "first"
        })
        .reset_index()
    )
    return grouped

# ---------------------------------------------------
# LOAD DATA
# ---------------------------------------------------
summits_df = load_summits()
counties_gdf = load_counties()
summits = spatial_join(summits_df, counties_gdf)

# ---------------------------------------------------
# SIDEBAR FILTERS
# ---------------------------------------------------
with st.sidebar:
    st.header("Filters")
    search_text = st.text_input("Search summit")
    all_counties = sorted({c.strip() for row in summits["CountyFull"].dropna() for c in row.split(",")})
    selected_county = st.selectbox("County", ["All"] + all_counties)

# ---------------------------------------------------
# APPLY FILTERS
# ---------------------------------------------------
filtered = summits.copy()
if search_text:
    filtered = filtered[
        filtered["SummitName"].str.contains(search_text, case=False) |
        filtered["SummitCode"].str.contains(search_text, case=False)
    ]
if selected_county != "All":
    filtered = filtered[filtered["CountyFull"].str.contains(selected_county)]

st.metric("Visible Summits", len(filtered))

# ---------------------------------------------------
# LAYOUT
# ---------------------------------------------------
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Summit List")
    display_df = filtered[["SummitCode", "SummitName", "CountyFull"]].rename(
        columns={"SummitCode": "Summit", "SummitName": "Name", "CountyFull": "County"}
    ).sort_values("Name").reset_index(drop=True)

    # Use AgGrid or st.dataframe click workaround
    selected_summit = st.selectbox("Click summit to zoom map", [""] + display_df["Summit"].tolist())

with col2:
    st.subheader("Map")
    # Determine map center
    if selected_summit:
        row = display_df[display_df["Summit"] == selected_summit].iloc[0]
        map_center = [row["Latitude"], row["Longitude"]]
        zoom = 10
    elif not filtered.empty:
        map_center = [filtered["Latitude"].mean(), filtered["Longitude"].mean()]
        zoom = 5
    else:
        map_center = [39.8283, -98.5795]  # Center of continental USA
        zoom = 4

    m = folium.Map(location=map_center, zoom_start=zoom, tiles="OpenTopoMap")

    # Add county boundaries
    folium.GeoJson(
        counties_gdf,
        style_function=lambda x: {"color": "gray", "weight": 1, "fill": False},
        name="Counties"
    ).add_to(m)

    # Add summit markers with clustering
    cluster = MarkerCluster().add_to(m)
    for _, summit in filtered.iterrows():
        color = "blue" if summit["SummitCode"] == selected_summit else "red"
        folium.CircleMarker(
            location=[summit["Latitude"], summit["Longitude"]],
            radius=6,
            color=color,
            fill=True,
            fill_opacity=0.7,
            popup=f"<b>{summit['SummitName']}</b><br>Code: {summit['SummitCode']}<br>County: {summit['CountyFull']}"
        ).add_to(cluster)


    st_folium(m, width=800, height=600)
