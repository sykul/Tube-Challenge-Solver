#!/usr/bin/env python3

import os
import json
import math
import networkx as nx
import pandas as pd
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point
from shapely.ops import nearest_points

# =========================
# Assumptions (explicit)
# =========================

ASSUMPTIONS = {
    "metro_cruise_speed_kmh": 40.0,
    "avg_walk_speed_kmh": 4.8,

    "dwell_time_s": 30,
    "minimum_platform_access_time_s": 120,
    "minimum_transfer_overhead_s": 180,
    "terminal_turnback_penalty_s": 300,
}

# =========================
# Helpers
# =========================

def seconds_per_meter(speed_kmh: float) -> float:
    return 3600.0 / (speed_kmh * 1000.0)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


# =========================
# 1. Extract OSM data
# =========================

def extract_osm_data(place: str):
    print("Extracting stations...")
    stations = ox.geometries_from_place(
        place,
        tags={"railway": "station", "station": "subway"}
    )

    print("Extracting subway routes...")
    routes = ox.geometries_from_place(
        place,
        tags={"route": "subway"}
    )

    print("Extracting subway tracks...")
    tracks = ox.geometries_from_place(
        place,
        tags={"railway": "subway"}
    )

    print("Extracting pedestrian network...")
    G_walk = ox.graph_from_place(place, network_type="walk")

    return stations, routes, tracks, G_walk


# =========================
# 2. Build station table
# =========================

def build_station_table(stations_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    records = []
    seen = {}

    for _, row in stations_gdf.iterrows():
        osm_id = row["osmid"]
        if osm_id in seen:
            continue

        geom = row.geometry
        if geom.geom_type != "Point":
            geom = geom.centroid

        station_id = len(seen)
        seen[osm_id] = station_id

        records.append({
            "station_id": station_id,
            "osm_id": osm_id,
            "name": row.get("name", f"station_{station_id}"),
            "lat": geom.y,
            "lon": geom.x,
        })

    df = pd.DataFrame(records)
    return df


# =========================
# 3. Build line definitions
# =========================

def build_lines(routes_gdf: gpd.GeoDataFrame, station_df: pd.DataFrame):
    osm_to_station = dict(zip(station_df.osm_id, station_df.station_id))
    lines = {}

    for _, row in routes_gdf.iterrows():
        line_id = row.get("ref") or row.get("name")
        if not line_id:
            continue

        members = row.get("members")
        if not isinstance(members, list):
            continue

        seq = []
        for m in members:
            ref = m.get("ref")
            if ref in osm_to_station:
                seq.append(osm_to_station[ref])

        if len(seq) >= 2:
            lines[line_id] = {
                "name": row.get("name", line_id),
                "stations": seq
            }

    return lines


# =========================
# 4. Metro distance via track geometry
# =========================

def build_track_index(tracks_gdf: gpd.GeoDataFrame):
    tracks_gdf = tracks_gdf.to_crs(epsg=32651)  # UTM for Shanghai
    return tracks_gdf


def metro_distance(station_a, station_b, tracks_gdf):
    """
    Conservative implementation:
    - snap stations to nearest track geometry
    - use straight-line distance along that track's CRS
    """
    pt_a = Point(station_a["lon"], station_a["lat"])
    pt_b = Point(station_b["lon"], station_b["lat"])

    pt_a = gpd.GeoSeries([pt_a], crs=4326).to_crs(32651).iloc[0]
    pt_b = gpd.GeoSeries([pt_b], crs=4326).to_crs(32651).iloc[0]

    tracks_gdf["dist"] = tracks_gdf.geometry.distance(pt_a)
    track = tracks_gdf.sort_values("dist").iloc[0].geometry

    proj_a = nearest_points(track, pt_a)[0]
    proj_b = nearest_points(track, pt_b)[0]

    return proj_a.distance(proj_b)


# =========================
# 5. Walking admissibility rule
# =========================

def walking_is_admissible(dist_walk_m, euclid_m):
    walk_time = dist_walk_m * seconds_per_meter(
        ASSUMPTIONS["avg_walk_speed_kmh"]
    )

    optimistic_metro_time = euclid_m * seconds_per_meter(
        ASSUMPTIONS["metro_cruise_speed_kmh"]
    )

    min_overhead = (
        ASSUMPTIONS["dwell_time_s"]
        + ASSUMPTIONS["minimum_platform_access_time_s"]
    )

    return walk_time < optimistic_metro_time + min_overhead


# =========================
# 6. Build full graph
# =========================

def build_graph(stations, lines, tracks_gdf, G_walk):
    G = nx.DiGraph()

    # Add stations as nodes
    for _, s in stations.iterrows():
        G.add_node(
            s.station_id,
            name=s.name,
            lat=s.lat,
            lon=s.lon
        )

    # Metro edges
    for lid, line in lines.items():
        seq = line["stations"]
        for a, b in zip(seq, seq[1:]):
            sa = stations.loc[stations.station_id == a].iloc[0]
            sb = stations.loc[stations.station_id == b].iloc[0]

            dist = metro_distance(sa, sb, tracks_gdf)
            time_s = (
                dist * seconds_per_meter(
                    ASSUMPTIONS["metro_cruise_speed_kmh"]
                )
                + ASSUMPTIONS["dwell_time_s"]
            )

            G.add_edge(a, b, mode="metro", line=lid,
                       distance_m=dist, time_s=time_s)
            G.add_edge(b, a, mode="metro", line=lid,
                       distance_m=dist, time_s=time_s)

    # Walking edges (filtered)
    walk_nodes = {
        s.station_id: ox.distance.nearest_nodes(
            G_walk, s.lon, s.lat
        )
        for _, s in stations.iterrows()
    }

    for i, s1 in stations.iterrows():
        for j, s2 in stations.iterrows():
            if i >= j:
                continue

            euclid_m = ox.distance.great_circle_vec(
                s1.lat, s1.lon, s2.lat, s2.lon
            )

            if euclid_m > 1500:
                continue

            d_walk = nx.shortest_path_length(
                G_walk,
                walk_nodes[s1.station_id],
                walk_nodes[s2.station_id],
                weight="length"
            )

            if walking_is_admissible(d_walk, euclid_m):
                t = d_walk * seconds_per_meter(
                    ASSUMPTIONS["avg_walk_speed_kmh"]
                )

                G.add_edge(s1.station_id, s2.station_id,
                           mode="walk", distance_m=d_walk, time_s=t)
                G.add_edge(s2.station_id, s1.station_id,
                           mode="walk", distance_m=d_walk, time_s=t)

    return G


# =========================
# Main
# =========================

def main():
    place = "Shanghai, China"
    ensure_dir("output")

    stations_gdf, routes_gdf, tracks_gdf, G_walk = extract_osm_data(place)

    stations = build_station_table(stations_gdf)
    lines = build_lines(routes_gdf, stations)
    tracks_gdf = build_track_index(tracks_gdf)

    G = build_graph(stations, lines, tracks_gdf, G_walk)

    nx.write_gpickle(G, "output/shanghai_graph.gpickle")
    stations.to_csv("output/stations.csv", index=False)

    with open("output/lines.json", "w") as f:
        json.dump(lines, f, indent=2)

    print("Graph built.")
    print(f"Stations: {G.number_of_nodes()}")
    print(f"Edges: {G.number_of_edges()}")


if __name__ == "__main__":
    main()
