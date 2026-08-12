"""Side panel: fleet, orders, dispatch, upgrades."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from graphcabs.config import (
    CAB_COST,
    FUEL_DRAIN_PER_NODE,
    MAX_MISSED_PER_DAY,
    REFUEL_COST,
    TICK_MS,
    UPGRADE_COSTS,
)
from graphcabs.game import GameEngine
from graphcabs.graph import route_label
from graphcabs.models import Cab, Ride

STYLESHEET = """
QWidget#SidePanel {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f8fafc, stop:1 #f1f5f9);
    font-family: "Segoe UI", "Noto Sans Georgian", Arial, sans-serif;
    color: #1e293b;
}
QFrame#HeaderCard {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QLabel#SectionTitle {
    color: #64748b;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.4px;
    padding: 4px 0 8px 0;
}
QLabel#HeaderLabel {
    color: #94a3b8;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.6px;
}
QLabel#BalanceValue {
    color: #16a34a;
    font-size: 24px;
    font-weight: 700;
}
QLabel#StrikesValue {
    color: #ef4444;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 3px;
}
QLabel#DistancePreview {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    color: #2563eb;
    font-size: 12px;
    padding: 10px 12px;
}
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    font-size: 12px;
    gridline-color: #f1f5f9;
    outline: none;
    selection-background-color: #dbeafe;
    selection-color: #1e3a8a;
}
QTableWidget::item {
    padding: 8px 6px;
    border: none;
}
QTableWidget::item:selected {
    background: #dbeafe;
    color: #1e3a8a;
}
QHeaderView::section {
    background: #f8fafc;
    color: #64748b;
    padding: 10px 8px;
    border: none;
    border-bottom: 1px solid #e2e8f0;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
QPushButton#DispatchButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34d399, stop:1 #10b981);
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
    padding: 14px;
    border: none;
    border-radius: 10px;
}
QPushButton#DispatchButton:hover:enabled {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2dd4a8, stop:1 #059669);
}
QPushButton#DispatchButton:disabled {
    background: #e2e8f0;
    color: #94a3b8;
}
QPushButton#RecruitButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
    color: #ffffff;
    font-weight: 600;
    padding: 10px 18px;
    border: none;
    border-radius: 10px;
}
QPushButton#RecruitButton:hover:enabled { background: #1d4ed8; }
QPushButton#RecruitButton:disabled { background: #e2e8f0; color: #94a3b8; }
QPushButton#ActionButton {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    padding: 8px 14px;
    border-radius: 8px;
    font-weight: 500;
    color: #334155;
}
QPushButton#ActionButton:hover:enabled {
    background: #f8fafc;
    border-color: #94a3b8;
}
QPushButton#ActionButton:disabled { color: #cbd5e1; border-color: #e2e8f0; }
QComboBox {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 6px 10px;
    color: #334155;
}
QSplitter::handle {
    background: #e2e8f0;
    border-radius: 3px;
    margin: 6px 0;
    height: 4px;
}
QSplitter::handle:hover { background: #94a3b8; }
"""


def _status_label(ride):
    return {"pending": "Live", "assigned": "Active", "completed": "Done", "missed": "Missed"}.get(ride.outcome, ride.outcome)


def _row_bg(status):
    return {
        "Live": QColor("#eff6ff"), "Active": QColor("#fff7ed"),
        "Done": QColor("#f8fafc"), "Missed": QColor("#fef2f2"),
    }.get(status, QColor("#ffffff"))


def _setup_table(table):
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(38)
    table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    table.horizontalHeader().setHighlightSections(False)
    table.setFocusPolicy(Qt.StrongFocus)


def _class_color(ride):
    return QColor("#7c3aed") if ride.ride_class == "vip" else QColor("#15803d")


class SidePanel(QWidget):
    def __init__(self, engine: GameEngine, on_cab_selected=None, on_preview_changed=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.on_cab_selected = on_cab_selected
        self.on_preview_changed = on_preview_changed
        self.setObjectName("SidePanel")
        self.setStyleSheet(STYLESHEET)

        self._picked_ride_id = None
        self._row_for_ride = {}
        self._row_for_cab = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        layout.addWidget(self._build_header())

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        splitter.addWidget(self._build_fleet_section())
        splitter.addWidget(self._build_orders_section())
        splitter.setSizes([260, 340])
        layout.addWidget(splitter, stretch=1)

        upgrade_row = QHBoxLayout()
        upgrade_row.setSpacing(8)
        upgrade_row.addWidget(QLabel("Upgrade driver:"))
        self._upgrade_cab = QComboBox()
        upgrade_row.addWidget(self._upgrade_cab, stretch=1)
        for key, label in [("fuel_tank", "Fuel"), ("stamina", "Stamina"), ("speed", "Speed")]:
            btn = QPushButton(f"{label} ₾{UPGRADE_COSTS[key]}")
            btn.setObjectName("ActionButton")
            btn.clicked.connect(lambda _c, k=key: self._buy_upgrade(k))
            upgrade_row.addWidget(btn)
        layout.addLayout(upgrade_row)

    def _build_header(self):
        card = QFrame()
        card.setObjectName("HeaderCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(28)

        balance_col = QVBoxLayout()
        balance_col.setSpacing(4)
        bal_lbl = QLabel("BALANCE")
        bal_lbl.setObjectName("HeaderLabel")
        balance_col.addWidget(bal_lbl)
        self._balance = QLabel()
        self._balance.setObjectName("BalanceValue")
        balance_col.addWidget(self._balance)

        strikes_col = QVBoxLayout()
        strikes_col.setSpacing(4)
        strikes_lbl = QLabel("STRIKES")
        strikes_lbl.setObjectName("HeaderLabel")
        strikes_col.addWidget(strikes_lbl)
        self._strikes = QLabel()
        self._strikes.setObjectName("StrikesValue")
        strikes_col.addWidget(self._strikes)

        row.addLayout(balance_col)
        row.addLayout(strikes_col)
        row.addStretch()
        self._recruit_btn = QPushButton(f"Hire Driver (-₾{CAB_COST:.0f})")
        self._recruit_btn.setObjectName("RecruitButton")
        self._recruit_btn.clicked.connect(lambda: self.engine.add_cab() and self.refresh_header())
        row.addWidget(self._recruit_btn)
        return card

    def _build_fleet_section(self):
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel("FLEET")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self._fleet_table = QTableWidget(0, 6)
        self._fleet_table.setHorizontalHeaderLabels(["#", "ID", "Driver", "Fuel", "Fatigue", "Status"])
        _setup_table(self._fleet_table)
        self._fleet_table.setColumnWidth(0, 30)
        self._fleet_table.setColumnWidth(1, 36)
        self._fleet_table.setColumnWidth(2, 130)
        self._fleet_table.itemSelectionChanged.connect(self._on_fleet_selected)
        layout.addWidget(self._fleet_table)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._refuel_btn = QPushButton(f"Refuel (₾{REFUEL_COST:.0f})")
        self._refuel_btn.setObjectName("ActionButton")
        self._refuel_btn.clicked.connect(self._refuel)
        self._rest_btn = QPushButton("Rest")
        self._rest_btn.setObjectName("ActionButton")
        self._rest_btn.clicked.connect(self._rest)
        actions.addWidget(self._refuel_btn)
        actions.addWidget(self._rest_btn)
        actions.addStretch()
        layout.addLayout(actions)
        return wrap

    def _build_orders_section(self):
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel("ORDERS")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self._orders_table = QTableWidget(0, 8)
        self._orders_table.setHorizontalHeaderLabels(
            ["#", "ID", "Customer", "Class", "Status", "Route", "Payout", "Fuel"]
        )
        _setup_table(self._orders_table)
        self._orders_table.setColumnWidth(0, 30)
        self._orders_table.setColumnWidth(1, 36)
        self._orders_table.setColumnWidth(2, 110)
        self._orders_table.setColumnWidth(3, 52)
        self._orders_table.setColumnWidth(5, 160)
        self._orders_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self._orders_table.itemSelectionChanged.connect(self._on_order_selected)
        self._orders_table.cellDoubleClicked.connect(lambda _r, _c: self._dispatch())
        layout.addWidget(self._orders_table)

        self._distance_label = QLabel("Pick a driver and a Live order.")
        self._distance_label.setObjectName("DistancePreview")
        self._distance_label.setWordWrap(True)
        layout.addWidget(self._distance_label)

        self._dispatch_btn = QPushButton("DISPATCH")
        self._dispatch_btn.setObjectName("DispatchButton")
        self._dispatch_btn.setEnabled(False)
        self._dispatch_btn.setCursor(Qt.PointingHandCursor)
        self._dispatch_btn.clicked.connect(self._dispatch)
        layout.addWidget(self._dispatch_btn)
        return wrap

    def selected_cab_id(self):
        rows = self._fleet_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._fleet_table.item(rows[0].row(), 1)
        return int(item.text()) if item else None

    def selected_ride_id(self):
        return self._picked_ride_id

    def select_cab(self, cab_id):
        row = self._row_for_cab.get(cab_id)
        if row is not None:
            self._fleet_table.blockSignals(True)
            self._fleet_table.selectRow(row)
            self._fleet_table.blockSignals(False)

    def select_ride(self, ride_id):
        self._picked_ride_id = ride_id
        row = self._row_for_ride.get(ride_id)
        if row is not None:
            self._orders_table.blockSignals(True)
            self._orders_table.selectRow(row)
            self._orders_table.blockSignals(False)
        self.refresh_dispatch_preview()

    def set_distance_text(self, text):
        self._distance_label.setText(text)

    def refresh_dispatch_preview(self):
        text, can_dispatch = self.engine.dispatch_preview(
            self.selected_cab_id(), self._picked_ride_id
        )
        self._distance_label.setText(text)
        self._dispatch_btn.setEnabled(can_dispatch)
        if self.on_preview_changed:
            self.on_preview_changed(text)
        return text

    def try_dispatch(self, ride_id, cab_id):
        ok = self.engine.dispatch(ride_id, cab_id)
        if ok:
            self.refresh_orders()
            self.refresh_dispatch_preview()
        return ok

    def refresh_header(self):
        self._balance.setText(f"₾{self.engine.money:,.0f}")
        missed = self.engine.missed_rides_today
        slots = ["✕" if i < missed else "·" for i in range(MAX_MISSED_PER_DAY)]
        self._strikes.setText("  ".join(slots))
        self._recruit_btn.setEnabled(self.engine.money >= CAB_COST)
        self._refresh_upgrade_combo()
        self._refresh_fleet_buttons()

    def refresh_fleet(self):
        self._fleet_table.setRowCount(0)
        self._row_for_cab.clear()
        for i, cab in enumerate(self.engine.cabs, start=1):
            row = self._fleet_table.rowCount()
            self._fleet_table.insertRow(row)
            self._row_for_cab[cab.cab_id] = row
            status = cab.status.replace("_", " ").title()
            if cab.status == "resting":
                status = f"Resting ({cab.rest_ticks_remaining * TICK_MS / 1000:.0f}s)"
            for col, text in enumerate([str(i), str(cab.cab_id), cab.name,
                                        f"{cab.fuel:.0f}%", f"{cab.tiredness:.0f}%", status]):
                item = QTableWidgetItem(text)
                if col == 2:
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                    font = QFont()
                    font.setWeight(500)
                    item.setFont(font)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                if col == 1:
                    item.setData(Qt.UserRole, cab.cab_id)
                self._fleet_table.setItem(row, col, item)
        self._refresh_upgrade_combo()
        self._refresh_fleet_buttons()

    def update_cab(self, cab: Cab):
        row = self._row_for_cab.get(cab.cab_id)
        if row is None:
            self.refresh_fleet()
            return
        status = cab.status.replace("_", " ").title()
        if cab.status == "resting":
            status = f"Resting ({cab.rest_ticks_remaining * TICK_MS / 1000:.0f}s)"
        for col, text in [(3, f"{cab.fuel:.0f}%"), (4, f"{cab.tiredness:.0f}%"), (5, status)]:
            self._fleet_table.item(row, col).setText(text)
        self._refresh_fleet_buttons()

    def refresh_orders(self):
        saved = self._picked_ride_id
        self._orders_table.blockSignals(True)
        self._orders_table.setRowCount(0)
        self._row_for_ride.clear()
        rides = [r for r in self.engine.all_rides if r.day == self.engine.day]
        for i, ride in enumerate(rides, start=1):
            row = self._orders_table.rowCount()
            self._orders_table.insertRow(row)
            self._row_for_ride[ride.ride_id] = row
            status = _status_label(ride)
            bg = _row_bg(status)
            route = self._route_text(ride)
            fuel = f"{max(2, len(ride.route_path)) * FUEL_DRAIN_PER_NODE:.0f}%"
            cells = [
                str(i), str(ride.ride_id), ride.passenger_name, ride.ride_class_label,
                status, route, f"₾{ride.fare:.2f}", fuel,
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(bg)
                if col == 1:
                    item.setData(Qt.UserRole, ride.ride_id)
                if col in (2, 5):
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                if col == 3:
                    item.setForeground(_class_color(ride))
                if col == 4 and status == "Live":
                    item.setForeground(QColor("#2563eb"))
                if col == 4 and status == "Missed":
                    item.setForeground(QColor("#dc2626"))
                self._orders_table.setItem(row, col, item)
        if saved in self._row_for_ride:
            self._picked_ride_id = saved
            self._orders_table.selectRow(self._row_for_ride[saved])
        else:
            self._picked_ride_id = None
        self._orders_table.blockSignals(False)
        self.refresh_dispatch_preview()

    def tick_update(self):
        for ride_id, row in list(self._row_for_ride.items()):
            ride = self._find_ride(ride_id)
            if ride and ride.outcome == "pending":
                item = self._orders_table.item(row, 5)
                if item:
                    item.setText(self._route_text(ride))
        if self.selected_cab_id() and self._picked_ride_id:
            self.refresh_dispatch_preview()

    def _route_text(self, ride: Ride):
        try:
            route = route_label(self.engine.city_graph, ride.pickup_node, ride.dropoff_node)
        except KeyError:
            route = "Unknown"
        if ride.outcome == "pending":
            route += f" ({int(ride.ticks_remaining * TICK_MS / 1000)}s)"
        return route

    def _find_ride(self, ride_id):
        for ride in self.engine.all_rides:
            if ride.ride_id == ride_id:
                return ride
        return None

    def _on_fleet_selected(self):
        cab_id = self.selected_cab_id()
        self._refresh_fleet_buttons()
        self.refresh_dispatch_preview()
        if cab_id is not None and self.on_cab_selected:
            self.on_cab_selected(cab_id)

    def _on_order_selected(self):
        self._picked_ride_id = None
        rows = self._orders_table.selectionModel().selectedRows()
        if rows:
            item = self._orders_table.item(rows[0].row(), 1)
            if item:
                self._picked_ride_id = item.data(Qt.UserRole)
        self.refresh_dispatch_preview()

    def _dispatch(self):
        ride_id = self._picked_ride_id
        cab_id = self.selected_cab_id()
        if ride_id is None or cab_id is None:
            return
        ride = self._find_ride(ride_id)
        if ride is None or ride.outcome != "pending":
            self.refresh_dispatch_preview()
            return
        cab = next((c for c in self.engine.cabs if c.cab_id == cab_id), None)
        if cab and cab.status != "idle":
            self.refresh_dispatch_preview()
            return
        if self.engine.dispatch(ride_id, cab_id):
            self.refresh_orders()
            self.refresh_dispatch_preview()
        else:
            self._distance_label.setText("Dispatch failed — no valid route.")
            self._dispatch_btn.setEnabled(False)

    def _refuel(self):
        cab_id = self.selected_cab_id()
        if cab_id is not None:
            self.engine.refuel_cab(cab_id)

    def _rest(self):
        cab_id = self.selected_cab_id()
        if cab_id is not None:
            self.engine.rest_cab(cab_id)

    def _buy_upgrade(self, upgrade_type):
        cab_id = self._upgrade_cab.currentData()
        if cab_id is not None:
            self.engine.buy_upgrade(cab_id, upgrade_type)
            self.refresh_header()

    def _refresh_upgrade_combo(self):
        current = self._upgrade_cab.currentData()
        self._upgrade_cab.clear()
        for cab in self.engine.cabs:
            self._upgrade_cab.addItem(cab.name, cab.cab_id)
        if current is not None:
            idx = self._upgrade_cab.findData(current)
            if idx >= 0:
                self._upgrade_cab.setCurrentIndex(idx)

    def _refresh_fleet_buttons(self):
        cab_id = self.selected_cab_id()
        cab = next((c for c in self.engine.cabs if c.cab_id == cab_id), None)
        if cab is None:
            self._refuel_btn.setEnabled(False)
            self._rest_btn.setEnabled(False)
            return
        self._refuel_btn.setEnabled(cab.fuel <= 90 and self.engine.money >= REFUEL_COST)
        self._rest_btn.setEnabled(cab.status == "idle")
