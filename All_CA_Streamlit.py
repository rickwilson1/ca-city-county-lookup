import math
import requests
import streamlit as st

# ---------------------------------------------------
# ArcGIS REST endpoints for California
# ---------------------------------------------------
COUNTY_FS_QUERY = "https://services.gis.ca.gov/arcgis/rest/services/Boundaries/CA_Counties/FeatureServer/0/query"
CITY_MS_QUERY   = "https://services.gis.ca.gov/arcgis/rest/services/Boundaries/Incorporated_Cities/MapServer/0/query"
GEOCODE_URL     = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"


# ---------------------------------------------------
# Helpers
# ---------------------------------------------------
def geocode_address(address: str):
    """Convert a street address into latitude/longitude using ArcGIS World Geocoder."""
    params = {
        "f": "json",
        "singleLine": address,
        "outFields": "Match_addr,Addr_type",
        "maxLocations": 1
    }
    r = requests.get(GEOCODE_URL, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data.get("candidates"):
        return None, None, None
    candidate = data["candidates"][0]
    loc = candidate["location"]
    match_addr = candidate.get("address", "")
    postal_city = match_addr.split(",")[1].strip() if "," in match_addr else None
    return loc["y"], loc["x"], postal_city  # lat, lon, postal_city


def wgs84_to_web_mercator(lat: float, lon: float):
    """Convert WGS84 latitude/longitude to Web Mercator (EPSG:3857)."""
    max_lat = 85.05112878
    lat = max(min(lat, max_lat), -max_lat)
    origin_shift = 20037508.342789244
    x = lon * origin_shift / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * origin_shift / math.pi
    return x, y


def query_polygon_layer_point(x_merc: float, y_merc: float, url: str, out_fields="*"):
    """Query a polygon layer (county or city) with a point in Web Mercator coords."""
    params = {
        "f": "json",
        "where": "1=1",
        "geometry": f"{x_merc},{y_merc}",
        "geometryType": "esriGeometryPoint",
        "inSR": "102100",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "false",
        "outFields": out_fields
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    feats = data.get("features") or []
    return feats[0]["attributes"] if feats else None


def extract_first(attrs: dict, keys):
    """Return the first non-empty value among candidate keys."""
    if not attrs:
        return None
    for k in keys:
        v = attrs.get(k)
        if v not in (None, "", " "):
            return v
    return None


def get_city_county(address: str):
    """Return postal city, incorporated city/unincorporated, and county."""
    lat, lon, postal_city = geocode_address(address)
    if not lat or not lon:
        return None

    x, y = wgs84_to_web_mercator(lat, lon)

    county_attrs = query_polygon_layer_point(
        x, y, COUNTY_FS_QUERY, out_fields="County,POLYGON_NM"
    )
    county_name = extract_first(county_attrs, ["County", "POLYGON_NM"])

    city_attrs = query_polygon_layer_point(
        x, y, CITY_MS_QUERY, out_fields="NAME"
    )
    city_name = extract_first(city_attrs, ["NAME"])

    if city_name is None:
        city_label = "Unincorporated"
    else:
        city_label = city_name

    return {
        "address": address,
        "latitude": lat,
        "longitude": lon,
        "postal_city": postal_city,
        "county": county_name,
        "city": city_label
    }


# ---------------------------------------------------
# Streamlit App UI
# ---------------------------------------------------
st.set_page_config(page_title="California City/County Lookup", layout="centered")
st.title("🏙️ California City/County Lookup")
st.write("Enter a California address to find its county and whether it’s in an incorporated city.")

# Address input
user_address = st.text_input("Enter a California address:")

if user_address:
    with st.spinner("Looking up address..."):
        try:
            result = get_city_county(user_address)
            if result:
                st.success("✅ Lookup complete")

                # Nicely formatted results
                st.subheader("Results")
                st.markdown(f"**📍 Address Entered:** {result['address']}")
                st.markdown(f"**🌐 Latitude / Longitude:** {result['latitude']}, {result['longitude']}")
                st.markdown(f"**🏤 Postal City (mailing):** {result['postal_city']}")
                st.markdown(f"**🏛️ County:** {result['county']}")
                st.markdown(f"**🏙️ Incorporated City:** {result['city']}")
            else:
                st.error("Could not geocode that address. Please try again.")
        except Exception as e:
            st.error(f"Error: {e}")

# Sticky footer disclaimer
st.markdown(
    """
    <style>
    .reportview-container .main footer {visibility: hidden;} /* hide default footer */
    .footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #ffffff;
        color: gray;
        text-align: center;
        font-size: 12px;
        padding: 6px;
        border-top: 1px solid #e6e6e6;
        z-index: 100;
    }
    </style>
    <div class="footer">
        City and county determinations in this tool are based on the official California statewide GIS boundary datasets.
    </div>
    """,
    unsafe_allow_html=True
)

