"""Tbilisi street graph and pathfinding."""

import math
import random
from pathlib import Path

import networkx as nx
import osmnx as ox

from graphcabs.config import GRAPH_FILE, TBILISI_PLACE


class CityGraph:
    def __init__(self):
        graph_path = Path(GRAPH_FILE)
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        if graph_path.exists():
            print(f"Loading Tbilisi graph from {graph_path}...")
            self._graph = ox.load_graphml(graph_path)
        else:
            print(f"Downloading street graph for {TBILISI_PLACE}...")
            self._graph = ox.graph_from_place(TBILISI_PLACE, network_type="drive")
            ox.save_graphml(self._graph, graph_path)
        print(f"Graph ready: {self._graph.number_of_nodes()} nodes.")
        self._keys = {int(k): k for k in self._graph.nodes}
        self._node_list = list(self._keys.keys())

    @property
    def graph(self):
        return self._graph

    @staticmethod
    def to_node_id(node_id):
        return int(node_id)

    def resolve_key(self, node_id):
        key = self._keys.get(self.to_node_id(node_id))
        if key is None:
            raise KeyError(f"Unknown node: {node_id}")
        return key

    def has_node(self, node_id):
        return self.to_node_id(node_id) in self._keys

    def random_node(self):
        return random.choice(self._node_list)

    def node_coords(self, node_id):
        data = self._graph.nodes[self.resolve_key(node_id)]
        return float(data["y"]), float(data["x"])

    def all_node_coords(self):
        return {node_id: self.node_coords(node_id) for node_id in self._node_list}


# Tbilisi district bounding boxes (lat / lon).
_DISTRICTS = (
    ("Vake", 41.698, 41.718, 44.752, 44.788),
    ("Saburtalo", 41.718, 41.748, 44.738, 44.778),
    ("Mtatsminda", 41.688, 41.705, 44.788, 44.812),
    ("Old Tbilisi", 41.685, 41.698, 44.802, 44.822),
    ("Vera", 41.708, 41.722, 44.772, 44.798),
    ("Didube", 41.738, 41.758, 44.752, 44.782),
    ("Gldani", 41.752, 41.778, 44.768, 44.808),
    ("Isani", 41.678, 41.702, 44.822, 44.862),
    ("Samgori", 41.668, 41.692, 44.858, 44.902),
    ("Airport", 41.662, 41.678, 44.938, 44.968),
    ("Nadzaladevi", 41.728, 41.752, 44.808, 44.842),
    ("Chughureti", 41.702, 41.718, 44.788, 44.812),
    ("Krtsanisi", 41.655, 41.678, 44.812, 44.852),
    ("Avlabari", 41.688, 41.702, 44.812, 44.832),
    ("Temka", 41.708, 41.728, 44.858, 44.892),
    ("Varketili", 41.692, 41.708, 44.882, 44.912),
    ("Dighomi", 41.758, 41.778, 44.728, 44.758),
)


def _district_at(lat, lon):
    for name, south, north, west, east in _DISTRICTS:
        if south <= lat <= north and west <= lon <= east:
            return name
    best, best_dist = "Tbilisi", float("inf")
    for name, south, north, west, east in _DISTRICTS:
        clat, clon = (south + north) / 2, (west + east) / 2
        dist = (lat - clat) ** 2 + (lon - clon) ** 2
        if dist < best_dist:
            best, best_dist = name, dist
    return best


def route_label(graph, pickup_node, dropoff_node):
    plat, plon = graph.node_coords(pickup_node)
    dlat, dlon = graph.node_coords(dropoff_node)
    return f"{_district_at(plat, plon)} → {_district_at(dlat, dlon)}"


class PathFinder:
    def __init__(self, city_graph):
        self._graph = city_graph
        self._nx = city_graph.graph

    def _haversine(self, lat1, lon1, lat2, lon2):
        radius = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _heuristic(self, dest_node):
        dest_lat, dest_lon = self._graph.node_coords(dest_node)

        def estimate(node_id, _neighbor):
            lat, lon = self._graph.node_coords(node_id)
            return self._haversine(lat, lon, dest_lat, dest_lon)

        return estimate

    def find_path(self, origin_node, dest_node):
        origin = self._graph.to_node_id(origin_node)
        dest = self._graph.to_node_id(dest_node)
        if origin == dest:
            return [origin]
        try:
            path = nx.astar_path(
                self._nx,
                self._graph.resolve_key(origin),
                self._graph.resolve_key(dest),
                heuristic=self._heuristic(dest),
                weight="length",
            )
            return [self._graph.to_node_id(n) for n in path]
        except (nx.NetworkXNoPath, nx.NodeNotFound, KeyError):
            return []

    def path_distance_meters(self, path):
        if len(path) < 2:
            return 0.0
        total = 0.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_data = self._nx.get_edge_data(self._graph.resolve_key(u), self._graph.resolve_key(v))
            if edge_data:
                length = next(iter(edge_data.values())).get("length")
                if length is not None:
                    total += float(length)
                    continue
            lat1, lon1 = self._graph.node_coords(u)
            lat2, lon2 = self._graph.node_coords(v)
            total += self._haversine(lat1, lon1, lat2, lon2)
        return total

    def distance_between(self, origin_node, dest_node):
        path = self.find_path(origin_node, dest_node)
        if not path:
            return [], 0.0
        return path, self.path_distance_meters(path)

    def format_distance(self, meters):
        if meters >= 1000:
            return f"{meters / 1000:.2f} km"
        return f"{meters:.0f} m"
