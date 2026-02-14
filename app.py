import streamlit as st
import json
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import pydeck as pdk

st.set_page_config(layout="wide")
st.title("🇺🇸 SOTA USA Summits by County")

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

    # Convert summits to GeoDataFrame
    geometry = [
        Point(xy) for xy in zip(summits_df["Longitude"], summits_df["Latitude"])
    ]

    summits_gdf = gpd.GeoDataFrame(
        summits_df,
        geometry=geometry,
        crs="EPSG:4326"
    )

    # Spatial join (intersects handles boundary case)
    joined = gpd.sjoin(
        summits_gdf,
        counties_gdf,
        how="left",
        predicate="intersects"
    )

    # Build readable county + state name
    joined["CountyFull"] = (
        joined["NAME"] + " County, " + joined["STATE"]
    )

    # Aggregate counties per summit
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
# LOAD + JOIN
# ---------------------------------------------------

summits_df = load_summits()
counties_gdf = load_counties()
summits = spatial_join(summits_df, counties_gdf)

# ---------------------------------------------------
# SIDEBAR FILTERS
# ---------------------------------------------------

st.sidebar.header("Filters")

search_text = st.sidebar.text_input("Search summit name or code")

# Extract unique counties
all_counties = sorted(
    {
        c.strip()
        for row in summits["CountyFull"].dropna()
        for c in row.split(",")
    }
)

selected_county = st.sidebar.selectbox(
    "Filter by County",
    ["All"] + all_counties
)

min_points = st.sidebar.slider(
    "Minimum SOTA Points",
    min_value=0,
    max_value=int(summits["Points"].max()),
    value=0
)

# ---------------------------------------------------
# APPLY FILTERS
# ---------------------------------------------------

filtered = summits.copy()

if search_text:
    filtered = filtered[
        filtered["SummitName"].str.contains(search_text, case=False)
        | filtered["SummitCode"].str.contains(search_text, case=False)
    ]

if selected_county != "All":
    filtered = filtered[
        filtered["CountyFull"].str.contains(selected_county)
    ]

filtered = filtered[filtered["Points"] >= min_points]

# ---------------------------------------------------
# LAYOUT
# ---------------------------------------------------

col1, col2 = st.columns([1, 2])

# ---------------- TABLE ----------------

with col1:
    st.subheader("Summit List")
    st.write(f"{len(filtered)} summits")

    st.dataframe(
        filtered.sort_values("SummitName"),
        use_container_width=True
    )

# ---------------- MAP ----------------

with col2:
    st.subheader("Map")

    if not filtered.empty:

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=filtered,
            get_position="[Longitude, Latitude]",
            get_radius=600,
            pickable=True,
        )

        view_state = pdk.ViewState(
            latitude=filtered["Latitude"].mean(),
            longitude=filtered["Longitude"].mean(),
            zoom=6,
        )

        tooltip = {
            "html": """
                <b>{SummitName}</b><br/>
                Code: {SummitCode}<br/>
                Points: {Points}<br/>
                County: {CountyFull}
            """,
            "style": {"backgroundColor": "steelblue", "color": "white"},
        }

        st.pydeck_chart(
            pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip=tooltip,
            )
        )

    else:
        st.info("No summits match filters.")
