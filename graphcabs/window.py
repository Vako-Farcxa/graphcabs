"""Main application window."""

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QAction, QMainWindow, QMessageBox, QSplitter

from graphcabs.config import MAX_MISSED_PER_DAY, UI_REFRESH_MS
from graphcabs.game import GameEngine
from graphcabs.history import show_history_dialog
from graphcabs.map import MapWidget
from graphcabs.models import Cab
from graphcabs.panels import SidePanel

WINDOW_STYLE = """
QMainWindow { background: #ffffff; }
QStatusBar {
    background: #f8fafc;
    color: #475569;
    border-top: 1px solid #e2e8f0;
    padding: 4px 12px;
    font-size: 12px;
}
QMenuBar {
    background: #ffffff;
    color: #334155;
    border-bottom: 1px solid #e2e8f0;
    padding: 2px 0;
    font-size: 13px;
}
QMenuBar::item:selected { background: #f1f5f9; border-radius: 4px; }
QMenu {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item { padding: 6px 24px; border-radius: 4px; }
QMenu::item:selected { background: #eff6ff; color: #1d4ed8; }
QSplitter::handle {
    background: #e2e8f0;
    width: 4px;
    margin: 0 2px;
}
QSplitter::handle:hover { background: #94a3b8; }
"""


class MainWindow(QMainWindow):
    def __init__(self, engine: GameEngine):
        super().__init__()
        self.engine = engine
        self.setWindowTitle("GraphCabs — Tbilisi Taxi Dispatcher")
        self.resize(1280, 820)
        self.setStyleSheet(WINDOW_STYLE)
        font = QFont("Segoe UI", 10)
        font.setStyleStrategy(QFont.PreferAntialias)
        self.setFont(font)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)
        self._map = MapWidget(engine.city_graph)
        self._panel = SidePanel(
            engine,
            on_cab_selected=self._on_cab_selected,
            on_preview_changed=self._map.set_distance_preview,
        )
        splitter.addWidget(self._map)
        splitter.addWidget(self._panel)
        splitter.setSizes([860, 420])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        game_menu = self.menuBar().addMenu("Game")
        history_action = QAction("Past Games…", self)
        history_action.triggered.connect(lambda: show_history_dialog(self))
        game_menu.addAction(history_action)

        view_menu = self.menuBar().addMenu("View")
        zoom_in = QAction("Zoom In", self)
        zoom_in.setShortcut("Ctrl++")
        zoom_in.triggered.connect(lambda: self._map._change_zoom(1.25))
        view_menu.addAction(zoom_in)
        zoom_out = QAction("Zoom Out", self)
        zoom_out.setShortcut("Ctrl+-")
        zoom_out.triggered.connect(lambda: self._map._change_zoom(0.8))
        view_menu.addAction(zoom_out)
        reset = QAction("Reset Map View", self)
        reset.triggered.connect(self._map.reset_view)
        view_menu.addAction(reset)

        engine.ride_spawned.connect(lambda _r: self._refresh_orders())
        engine.ride_expired.connect(lambda _r: (self._update_status(), self._refresh_orders()))
        engine.ride_assigned.connect(self._on_ride_assigned)
        engine.ride_completed.connect(lambda _r: (self._refresh_orders(), self._update_status()))
        engine.cab_updated.connect(self._on_cab_updated)
        engine.money_changed.connect(lambda _m: (self._update_status(), self._panel.refresh_header()))
        engine.day_ended.connect(self._on_day_ended)
        engine.game_over.connect(lambda msg: QMessageBox.critical(self, "Game Over", msg))
        engine.fleet_updated.connect(self._on_fleet_updated)
        self._map.cab_clicked.connect(self._on_map_cab_clicked)
        self._map.ride_route_clicked.connect(self._on_map_ride_clicked)

        self._map.initialize_cabs(engine.cabs, engine.cab_nodes)
        self._panel.refresh_fleet()
        self._refresh_orders()
        self._update_status()

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(UI_REFRESH_MS)
        self._ui_timer.timeout.connect(self._ui_tick)
        self._ui_timer.start()

    def _ui_tick(self):
        self._panel.tick_update()
        self._panel.refresh_header()
        self._update_status()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            ride_id = self._panel.selected_ride_id()
            cab_id = self._panel.selected_cab_id()
            if ride_id and cab_id and self._try_dispatch(ride_id, cab_id):
                event.accept()
                return
        super().keyPressEvent(event)

    def _refresh_orders(self):
        self._map.set_orders(self.engine.pending_rides, self.engine.get_assigned_rides())
        self._panel.refresh_orders()

    def _on_ride_assigned(self, _ride):
        self._refresh_orders()
        self._panel.refresh_dispatch_preview()

    def _update_status(self):
        spawned, target = self.engine.day_orders_progress()
        orders = "New day — orders arriving soon" if self.engine.is_order_free_period else f"Orders: {spawned}/{target}"
        self.statusBar().showMessage(
            f"Day {self.engine.day} | Money: ₾{self.engine.money:.2f} | "
            f"Missed: {self.engine.missed_rides_today}/{MAX_MISSED_PER_DAY} | {orders}"
        )

    def _try_dispatch(self, ride_id, cab_id):
        if self._panel.try_dispatch(ride_id, cab_id):
            self._map.clear_distance_preview()
            cab_name = next(c.name for c in self.engine.cabs if c.cab_id == cab_id)
            ride = self.engine.get_ride_by_id(ride_id)
            passenger = ride.passenger_name if ride else f"Ride #{ride_id}"
            self.statusBar().showMessage(f"{cab_name} dispatched to {passenger}", 5000)
            return True
        QMessageBox.warning(self, "Dispatch Failed", "Driver must be idle with a valid route.")
        return False

    def _on_cab_selected(self, cab_id):
        self._map.set_selected_cab(cab_id)
        self._panel.refresh_dispatch_preview()

    def _on_map_cab_clicked(self, cab_id):
        self._panel.select_cab(cab_id)
        self._on_cab_selected(cab_id)

    def _on_map_ride_clicked(self, ride_id):
        self._panel.select_ride(ride_id)
        self._panel.refresh_dispatch_preview()

    def _on_cab_updated(self, cab: Cab):
        if cab.status in ("to_pickup", "en_route"):
            self._map.update_cab(cab, self.engine.cab_nodes.get(cab.cab_id))
        elif cab.cab_id == self._map.selected_cab_id():
            self._map.update_cab(cab, self.engine.cab_nodes.get(cab.cab_id))
        self._panel.update_cab(cab)
        if cab.cab_id == self._panel.selected_cab_id():
            self._panel.refresh_dispatch_preview()

    def _on_fleet_updated(self):
        self._panel.refresh_fleet()
        self._panel.refresh_header()
        for cab in self.engine.cabs:
            self._map.update_cab(cab, self.engine.cab_nodes.get(cab.cab_id))
        self._update_status()

    def _on_day_ended(self, new_day):
        summary = self.engine.last_day_summary
        self._map.clear_distance_preview()
        self._refresh_orders()
        QMessageBox.information(
            self, f"Day {new_day - 1} Complete",
            f"Rides completed: {summary['completed']}\nMoney earned: ₾{summary['earned']:.2f}\n\nDay {new_day} starting.",
        )
        self._update_status()

    def closeEvent(self, event):
        self.engine.stop()
        super().closeEvent(event)
