"""Folium map (QWebEngineView + Leaflet)."""

from __future__ import annotations

import json
from typing import Any, Optional

import folium
from PyQt5.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from graphcabs.graph import CityGraph
from graphcabs.models import Cab, Ride

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView
except ImportError as exc:
    raise ImportError("Install PyQtWebEngine: pip install PyQtWebEngine") from exc

TBILISI_CENTER = (41.7151, 44.8271)
CAB_COLORS = {
    "idle": "#4285F4", "to_pickup": "#FBBC04", "en_route": "#E8710A",
    "resting": "#9AA0A6", "out_of_fuel": "#EA4335",
}


def _build_map_html(bounds, state, center=None, zoom=None):
    location = list(center or TBILISI_CENTER)
    zoom_start = zoom if zoom is not None else 12
    fleet_map = folium.Map(
        location=location,
        zoom_start=zoom_start,
        control_scale=True,
        tiles="OpenStreetMap",
        prefer_canvas=True,
        double_click_zoom=False,
    )
    if bounds and len(bounds) == 2 and center is None:
        fleet_map.fit_bounds(bounds, padding=(24, 24))
    map_name = fleet_map.get_name()
    payload = json.dumps(state or {"pending": [], "assigned": [], "cabs": []})
    cab_colors = json.dumps(CAB_COLORS)
    script = f"""
    <script>
    (function() {{
        const MAP_NAME = {json.dumps(map_name)};
        const CAB_COLORS = {cab_colors};
        let pendingLayer, assignedLayer, cabLayer, defaultBounds, leafletMap;
        const cabMarkers = {{}};

        function cabStyle(color, selected) {{
            return {{radius:10, fillColor:color, color:selected?"#174EA6":"#FFF",
                weight:selected?3.5:2.5, fillOpacity:1, interactive:false}};
        }}

        function notifyCab(id) {{
            if (window.graphcabsBridge) window.graphcabsBridge.cabClicked(id);
        }}
        function notifyRide(id, node) {{
            if (window.graphcabsBridge) window.graphcabsBridge.rideClicked(id, node);
        }}

        function drawRide(layer, ride, color, weight) {{
            if (!ride.path || ride.path.length < 2) return;
            L.polyline(ride.path, {{color:"#FFF",weight:weight+4,opacity:0.95,interactive:false}}).addTo(layer);
            const line = L.polyline(ride.path, {{color,weight,opacity:1,interactive:true}}).addTo(layer);
            const pickup = ride.path[0];
            L.circleMarker(pickup, {{radius:18,fillOpacity:0,opacity:0,interactive:true}})
                .addTo(layer).on("click", e => {{
                    L.DomEvent.stopPropagation(e); L.DomEvent.preventDefault(e);
                    notifyRide(ride.id, ride.pickupNode || 0);
                }});
            L.circleMarker(pickup, {{radius:7,color:"#FFF",fillColor:"#34A853",fillOpacity:1,weight:2.5,interactive:false}}).addTo(layer);
            L.circleMarker(ride.path[ride.path.length-1], {{radius:7,color:"#FFF",fillColor:"#EA4335",fillOpacity:1,weight:2.5,interactive:false}}).addTo(layer);
            line.on("click", e => {{
                L.DomEvent.stopPropagation(e); L.DomEvent.preventDefault(e);
                notifyRide(ride.id, ride.pickupNode || 0);
            }});
        }}

        function upsertCab(cab) {{
            const color = CAB_COLORS[cab.status] || CAB_COLORS.idle;
            const latlng = [cab.lat, cab.lng];
            let entry = cabMarkers[cab.id];
            if (!entry) {{
                const hit = L.circleMarker(latlng, {{
                    radius: 22, fillOpacity: 0, opacity: 0, interactive: true,
                }}).addTo(cabLayer);
                hit.on("click", e => {{
                    L.DomEvent.stopPropagation(e); L.DomEvent.preventDefault(e);
                    notifyCab(cab.id);
                }});
                const visual = L.circleMarker(latlng, cabStyle(color, !!cab.selected)).addTo(cabLayer);
                visual.bindTooltip(cab.name || "", {{direction:"right", offset:[12,0], sticky:true}});
                entry = cabMarkers[cab.id] = {{hit, visual}};
            }}
            entry.hit.setLatLng(latlng);
            entry.visual.setLatLng(latlng);
            entry.visual.setStyle(cabStyle(color, !!cab.selected));
            if (entry.visual.getTooltip()) entry.visual.setTooltipContent(cab.name || "");
        }}

        function clearCabMarkers() {{
            Object.keys(cabMarkers).forEach(id => {{
                cabLayer.removeLayer(cabMarkers[id].hit);
                cabLayer.removeLayer(cabMarkers[id].visual);
                delete cabMarkers[id];
            }});
        }}

        function renderState(state) {{
            if (!pendingLayer) return;
            pendingLayer.clearLayers();
            assignedLayer.clearLayers();
            clearCabMarkers();
            (state.pending||[]).forEach(r => drawRide(pendingLayer, r, "#0F9D58", 5));
            (state.assigned||[]).forEach(r => drawRide(assignedLayer, r, "#E8710A", 6));
            (state.cabs||[]).forEach(upsertCab);
        }}

        function init() {{
            const map = window[MAP_NAME];
            if (!map || !window.L) {{ setTimeout(init, 200); return; }}
            leafletMap = map;
            if (map.doubleClickZoom) map.doubleClickZoom.disable();
            map.createPane("pendingPane"); map.getPane("pendingPane").style.zIndex = 450;
            map.createPane("assignedPane"); map.getPane("assignedPane").style.zIndex = 460;
            map.createPane("cabPane"); map.getPane("cabPane").style.zIndex = 700;
            pendingLayer = L.layerGroup([], {{pane:"pendingPane"}}).addTo(map);
            assignedLayer = L.layerGroup([], {{pane:"assignedPane"}}).addTo(map);
            cabLayer = L.layerGroup([], {{pane:"cabPane"}}).addTo(map);
            defaultBounds = map.getBounds();
            map.on("moveend zoomend", () => {{
                const c = map.getCenter();
                window.graphcabsBridge.mapViewChanged(c.lat, c.lng, map.getZoom());
            }});
            window.graphcabsUpdate = s => renderState(s||{{pending:[],assigned:[],cabs:[]}});
            window.graphcabsUpdateCabs = cabs => {{
                if (!cabLayer) return;
                const seen = new Set();
                (cabs||[]).forEach(c => {{ seen.add(c.id); upsertCab(c); }});
                Object.keys(cabMarkers).forEach(id => {{
                    if (!seen.has(Number(id))) {{
                        cabLayer.removeLayer(cabMarkers[id].hit);
                        cabLayer.removeLayer(cabMarkers[id].visual);
                        delete cabMarkers[id];
                    }}
                }});
            }};
            window.graphcabsZoomBy = f => map.setZoom(map.getZoom() + Math.log2(f));
            window.graphcabsResetView = b => {{
                if (b && b.length===2) map.fitBounds(b, {{padding:[24,24]}});
                else if (defaultBounds) map.fitBounds(defaultBounds, {{padding:[24,24]}});
                else map.setView([41.7151,44.8271],12);
            }};
            window.graphcabsUpdate({payload});
            window.graphcabsMapInitialized = true;
            if (window.graphcabsBridge) window.graphcabsBridge.mapReady();
        }}
        document.readyState==="loading" ? document.addEventListener("DOMContentLoaded", init) : init();
    }})();
    </script>
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
    <script>new QWebChannel(qt.webChannelTransport, ch => {{
        window.graphcabsBridge = ch.objects.bridge;
        if (window.graphcabsMapInitialized) window.graphcabsBridge.mapReady();
    }});</script>
    """
    html = fleet_map.get_root().render()
    return html.replace("</body>", script + "</body>")


class _MapBridge(QObject):
    node_clicked = pyqtSignal(object)
    ride_route_clicked = pyqtSignal(int)
    cab_clicked = pyqtSignal(int)
    map_ready = pyqtSignal()
    view_changed = pyqtSignal(float, float, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view_lat, self._view_lon, self._view_zoom = 41.7151, 44.8271, 12

    @pyqtSlot(int)
    def cabClicked(self, cab_id):
        self.cab_clicked.emit(int(cab_id))

    @pyqtSlot(int, int)
    def rideClicked(self, ride_id, pickup_node):
        self.ride_route_clicked.emit(ride_id)
        self.node_clicked.emit(pickup_node)

    @pyqtSlot(float, float, float)
    def mapViewChanged(self, lat, lon, zoom):
        self._view_lat, self._view_lon = lat, lon
        self._view_zoom = int(zoom)
        self.view_changed.emit(lat, lon, int(zoom))

    @pyqtSlot()
    def mapReady(self):
        self.map_ready.emit()


class MapWidget(QWidget):
    node_clicked = pyqtSignal(object)
    ride_route_clicked = pyqtSignal(int)
    cab_clicked = pyqtSignal(int)

    def __init__(self, city_graph: CityGraph, parent=None):
        super().__init__(parent)
        self._city_graph = city_graph
        self._bounds = self._compute_bounds()
        self._pending_rides = []
        self._assigned_rides = []
        self._selected_cab_id = None
        self._cab_states = {}
        self._map_ready = False
        self._pending_js = []
        self._view_center = None
        self._view_zoom = None
        self._needs_full_render = False
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(200)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush_map)

        self.setMinimumSize(400, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._view = QWebEngineView(self)
        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        layout.addWidget(self._view)

        self._bridge = _MapBridge(self)
        self._bridge.cab_clicked.connect(self.cab_clicked.emit)
        self._bridge.ride_route_clicked.connect(self.ride_route_clicked.emit)
        self._bridge.node_clicked.connect(self.node_clicked.emit)
        self._bridge.map_ready.connect(self._on_map_ready)
        self._bridge.view_changed.connect(self._on_view_changed)

        channel = QWebChannel(self)
        channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(channel)

        self._overlay = QWidget(self._view)
        overlay_layout = QVBoxLayout(self._overlay)
        overlay_layout.setContentsMargins(8, 8, 8, 8)
        card_style = (
            "background:#ffffff;padding:10px 12px;border-radius:10px;"
            "border:1px solid #e2e8f0;font-size:12px;color:#475569;"
        )
        self._legend = QLabel("Scroll to zoom · drag to pan · 🟢 pickup 🔴 dropoff 🔵 cab")
        self._legend.setStyleSheet(card_style)
        overlay_layout.addWidget(self._legend)
        overlay_layout.addStretch()
        self._distance_label = QLabel("")
        self._distance_label.setStyleSheet(card_style + "color:#2563eb;font-weight:500;")
        self._distance_label.setWordWrap(True)
        overlay_layout.addWidget(self._distance_label)
        self._overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._overlay.setGeometry(self.rect())
        self._load_map_html()

    def resizeEvent(self, event):
        self._overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def _compute_bounds(self):
        coords = self._city_graph.all_node_coords()
        if not coords:
            return [[41.65, 44.75], [41.78, 44.95]]
        lats = [c[0] for c in coords.values()]
        lons = [c[1] for c in coords.values()]
        return [[min(lats), min(lons)], [max(lats), max(lons)]]

    def _path_to_latlng(self, path):
        return [[*self._city_graph.node_coords(n)] for n in path if self._city_graph.has_node(n)]

    def _cab_latlng(self, cab, node_id):
        path = cab.active_path
        if cab.status in ("to_pickup", "en_route") and path and 0 < cab.path_index < len(path):
            lat1, lon1 = self._city_graph.node_coords(path[cab.path_index - 1])
            lat2, lon2 = self._city_graph.node_coords(path[cab.path_index])
            t = 0.5
            return lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t
        return self._city_graph.node_coords(node_id)

    def _map_state(self):
        def ride_payload(ride):
            return {"id": ride.ride_id, "pickupNode": int(ride.pickup_node),
                    "path": self._path_to_latlng(ride.route_path)}
        return {
            "pending": [ride_payload(r) for r in self._pending_rides],
            "assigned": [ride_payload(r) for r in self._assigned_rides],
            "cabs": list(self._cab_states.values()),
        }

    def _load_map_html(self):
        html = _build_map_html(self._bounds, self._map_state(), self._view_center, self._view_zoom)
        self._view.setHtml(html, QUrl("qrc://"))
        self._map_ready = False

    def _on_view_changed(self, lat, lon, zoom):
        self._view_center = (lat, lon)
        self._view_zoom = zoom

    def _run_js(self, script):
        if not self._map_ready:
            self._pending_js.append(script)
            return
        self._view.page().runJavaScript(script)

    def _on_map_ready(self):
        self._map_ready = True
        self._view_center = (self._bridge._view_lat, self._bridge._view_lon)
        self._view_zoom = self._bridge._view_zoom
        self._needs_full_render = True
        self._flush_map()
        for script in self._pending_js:
            self._view.page().runJavaScript(script)
        self._pending_js.clear()

    def _schedule_flush(self, full=False):
        if full:
            self._needs_full_render = True
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush_map(self):
        if not self._map_ready:
            return
        if self._needs_full_render:
            self._needs_full_render = False
            self._run_js(f"window.graphcabsUpdate({json.dumps(self._map_state())})")
        else:
            self._run_js(f"window.graphcabsUpdateCabs({json.dumps(list(self._cab_states.values()))})")

    def _push_state(self, full=False):
        self._schedule_flush(full=full)

    def _change_zoom(self, factor):
        self._run_js(f"window.graphcabsZoomBy({factor})")

    def reset_view(self):
        self._view_center = None
        self._view_zoom = None
        self._run_js(f"window.graphcabsResetView({json.dumps(self._bounds)})")

    def update_cab(self, cab: Cab, node_id):
        if node_id is None:
            return
        lat, lon = self._cab_latlng(cab, int(node_id))
        self._cab_states[cab.cab_id] = {
            "id": cab.cab_id, "lat": lat, "lng": lon, "name": cab.name,
            "status": cab.status, "selected": cab.cab_id == self._selected_cab_id,
        }
        self._push_state(full=False)

    def set_selected_cab(self, cab_id):
        self._selected_cab_id = cab_id
        for cid, payload in self._cab_states.items():
            payload["selected"] = cid == cab_id
        self._push_state(full=False)

    def selected_cab_id(self):
        return self._selected_cab_id

    def set_orders(self, pending, assigned):
        self._pending_rides = list(pending)
        self._assigned_rides = list(assigned)
        self._push_state(full=True)

    def set_distance_preview(self, text, path=None, node_id=None):
        self._distance_label.setText(text)

    def clear_distance_preview(self):
        self.set_distance_preview("")

    def initialize_cabs(self, cabs, cab_nodes):
        for cab in cabs:
            node_id = cab_nodes.get(cab.cab_id)
            if node_id is None:
                continue
            lat, lon = self._cab_latlng(cab, int(node_id))
            self._cab_states[cab.cab_id] = {
                "id": cab.cab_id, "lat": lat, "lng": lon, "name": cab.name,
                "status": cab.status, "selected": cab.cab_id == self._selected_cab_id,
            }
        self._push_state(full=True)
