import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import pydeck as pdk
import json

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

    summits_gdf = gpd.GeoDataFrame(
        summits_df,
        geometry=geometry,
        crs="EPSG:4326"
    )

    joined = gpd.sjoin(
        summits_gdf,
        _counties_gdf,
        how="left",
        predicate="intersects"
    )

    # Convert FIPS → state abbreviation
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

    all_counties = sorted({
        c.strip() for row in summits["CountyFull"].dropna() for c in row.split(",")
    })

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
# TABLE + MAP LAYOUT
# ---------------------------------------------------
col1, col2 = st.columns([1, 2])

# ---------------- TABLE ----------------
with col1:
    st.subheader("Summit List")
    display_df = (
        filtered[["SummitCode", "SummitName", "CountyFull"]]
        .rename(columns={
            "SummitCode": "Summit",
            "SummitName": "Name",
            "CountyFull": "County"
        })
        .sort_values("Name")
        .reset_index(drop=True)
    )

    # Use selection to highlight map
    selected_index = st.experimental_data_editor(display_df, key="table_editor").index
    selected_code = None
    if len(selected_index) == 1:
        selected_code = display_df.iloc[selected_index[0]]["Summit"]

# ---------------- MAP ----------------
with col2:
    st.subheader("Map")
    if not filtered.empty:

        # Color for highlighting selected summit
        filtered["Color"] = filtered["SummitCode"].apply(
            lambda x: [0, 150, 255, 255] if x == selected_code else [200, 30, 0, 180]
        )

        # Summit layer (scatterplot)
        summit_layer = pdk.Layer(
            "ScatterplotLayer",
            data=filtered,
            get_position="[Longitude, Latitude]",
            get_radius=600,
            get_fill_color="Color",
            pickable=True,
            auto_highlight=True,
        )

        # County boundaries layer
        county_layer = pdk.Layer(
            "GeoJsonLayer",
            data=counties_gdf,
            stroked=True,
            filled=False,
            get_line_color=[80, 80, 80, 120],
            get_line_width=2,
            pickable=False,
        )

        # OpenTopoMap tile
        tile_layer = pdk.Layer(
            "TileLayer",
            data="https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
            min_zoom=0,
            max_zoom=19,
            tile_size=256
        )

        # Map view
        if selected_code:
            summit = filtered[filtered["SummitCode"] == selected_code].iloc[0]
            view_state = pdk.ViewState(
                latitude=summit["Latitude"],
                longitude=summit["Longitude"],
                zoom=10,
            )
        else:
            view_state = pdk.ViewState(
                latitude=filtered["Latitude"].mean(),
                longitude=filtered["Longitude"].mean(),
                zoom=6,
            )

        tooltip = {
            "html": """
                <b>{SummitName}</b><br/>
                Code: {SummitCode}<br/>
                County: {CountyFull}
            """
        }

        deck = pdk.Deck(
            layers=[tile_layer, county_layer, summit_layer],
            initial_view_state=view_state,
            tooltip=tooltip,
            map_style=None,
        )

        st.pydeck_chart(deck)
    else:
        st.info("No summits match filters.")
