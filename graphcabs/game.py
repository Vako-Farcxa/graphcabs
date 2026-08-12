"""Game loop, economy, dispatch, and ride spawning."""

import logging
import random

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from graphcabs.config import (
    BASE_FARE,
    BASE_RIDES_PER_DAY,
    BASIC_MAX_NODES,
    CAB_COST,
    DAY_DURATION_TICKS,
    DAY_START_GRACE_TICKS,
    DAY_ONE_GRACE_TICKS,
    DAY_ONE_SPAWN_INTERVAL_MULT,
    FARE_PER_KM,
    MAX_MISSED_PER_DAY,
    MAX_RIDES_PER_DAY,
    REFUEL_COST,
    RIDES_PER_EXTRA_CAB,
    TICK_MS,
    UPGRADE_COSTS,
    VIP_BASE_FARE,
    VIP_FARE_PER_KM,
    VIP_MIN_NODES,
    VIP_SPAWN_CHANCE,
)
from graphcabs.db import finish_game_run, log_day_summary, start_game_run
from graphcabs.graph import CityGraph, PathFinder, route_label
from graphcabs.models import Cab, Ride
from graphcabs.names import driver_name, passenger_name

logger = logging.getLogger(__name__)


class GameEngine(QObject):
    ride_spawned = pyqtSignal(object)
    ride_expired = pyqtSignal(object)
    ride_assigned = pyqtSignal(object)
    ride_completed = pyqtSignal(object)
    cab_updated = pyqtSignal(object)
    money_changed = pyqtSignal(float)
    day_ended = pyqtSignal(int)
    game_over = pyqtSignal(str)
    fleet_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.city_graph = CityGraph()
        self.pathfinder = PathFinder(self.city_graph)

        self.money = 100.0
        self.day = 1
        self.day_earned = 0.0
        self.cabs = []
        self.cab_nodes = {}
        self.all_rides = []
        self.pending_rides = []
        self._dropoff_paths = {}
        self._ride_by_cab = {}
        self.missed_rides_today = 0
        self.day_completed_rides = 0
        self.last_day_summary = {"completed": 0, "earned": 0.0}
        self._next_cab_id = 1
        self._next_ride_id = 1
        self._running = False
        self._game_over = False
        self._day_tick = 0
        self._rides_spawned_today = 0
        self._rides_target_today = 0
        self._day_grace_remaining = 0
        self._run_id = None
        self._run_finished = False
        self._run_total_earned = 0.0
        self._run_rides_completed = 0
        self._run_rides_missed = 0
        self._run_days_completed = 0

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)

    def start_game(self):
        if self.cabs:
            return
        for _ in range(2):
            cab = Cab(self._next_cab_id, driver_name())
            self._next_cab_id += 1
            self.cabs.append(cab)
            self.cab_nodes[cab.cab_id] = self.city_graph.random_node()
        self._running = True
        self._game_over = False
        self._run_id = start_game_run()
        self._run_finished = False
        self._run_total_earned = 0.0
        self._run_rides_completed = 0
        self._run_rides_missed = 0
        self._run_days_completed = 0
        self._begin_day()
        self._timer.start()
        self.fleet_updated.emit()

    def _begin_day(self):
        self._day_tick = 0
        self._rides_spawned_today = 0
        self._rides_target_today = self._rides_per_day(len(self.cabs))
        self._day_grace_remaining = DAY_ONE_GRACE_TICKS if self.day == 1 else DAY_START_GRACE_TICKS
        self.pending_rides.clear()
        self.all_rides.clear()

    def _end_day(self):
        self.last_day_summary = {"completed": self.day_completed_rides, "earned": self.day_earned}
        if self._run_id and not self._run_finished:
            log_day_summary(
                self._run_id,
                self.day,
                self.day_earned,
                self.day_completed_rides,
                self.missed_rides_today,
            )
            self._run_days_completed += 1
        self.day += 1
        self.day_earned = 0.0
        self.missed_rides_today = 0
        self.day_completed_rides = 0
        self.day_ended.emit(self.day)
        self._begin_day()

    def _rides_per_day(self, fleet_size):
        count = BASE_RIDES_PER_DAY + (max(1, fleet_size) - 1) * RIDES_PER_EXTRA_CAB
        return min(MAX_RIDES_PER_DAY, count)

    def _spawn_interval(self, fleet_size):
        interval = max(1, DAY_DURATION_TICKS // self._rides_per_day(fleet_size))
        if self.day == 1:
            interval = max(1, interval * DAY_ONE_SPAWN_INTERVAL_MULT)
        return interval

    def _should_spawn(self, day_tick, fleet_size):
        return day_tick > 0 and day_tick % self._spawn_interval(fleet_size) == 0

    def _fare_for_class(self, ride_class, route_path):
        meters = self.pathfinder.path_distance_meters(route_path)
        km = max(0.1, meters / 1000.0)
        if ride_class == "vip":
            return VIP_BASE_FARE + VIP_FARE_PER_KM * km
        return BASE_FARE + FARE_PER_KM * km

    def _generate_ride(self):
        want_vip = random.random() < VIP_SPAWN_CHANCE
        ride_class = "vip" if want_vip else "basic"
        min_nodes = VIP_MIN_NODES if want_vip else 2
        max_nodes = 999 if want_vip else BASIC_MAX_NODES

        for _ in range(50):
            pickup = self.city_graph.random_node()
            dropoff = self.city_graph.random_node()
            while dropoff == pickup:
                dropoff = self.city_graph.random_node()
            route_path = self.pathfinder.find_path(pickup, dropoff)
            node_count = len(route_path)
            if node_count < min_nodes or node_count > max_nodes:
                continue
            trip_meters = self.pathfinder.path_distance_meters(route_path)
            fare = self._fare_for_class(ride_class, route_path)
            ride = Ride(
                self._next_ride_id, pickup, dropoff, fare,
                self.day, route_path, ride_class,
                passenger_name=passenger_name(),
            )
            ride.trip_meters = trip_meters
            self._next_ride_id += 1
            return ride

        pickup = self.city_graph.random_node()
        dropoff = self.city_graph.random_node()
        while dropoff == pickup:
            dropoff = self.city_graph.random_node()
        route_path = self.pathfinder.find_path(pickup, dropoff) or [pickup, dropoff]
        node_count = max(2, len(route_path))
        if want_vip and node_count < VIP_MIN_NODES:
            ride_class = "basic"
        ride = Ride(
            self._next_ride_id, pickup, dropoff,
            self._fare_for_class(ride_class, route_path),
            self.day, route_path, ride_class,
            passenger_name=passenger_name(),
        )
        ride.trip_meters = self.pathfinder.path_distance_meters(route_path)
        self._next_ride_id += 1
        return ride

    def _assign_ride(self, ride, cab, cab_node):
        if cab.status != "idle":
            return False
        pickup_path = self.pathfinder.find_path(cab_node, ride.pickup_node)
        dropoff_path = self.pathfinder.find_path(ride.pickup_node, ride.dropoff_node)
        if not pickup_path or not dropoff_path:
            return False
        cab.assign_route(pickup_path, "to_pickup")
        ride.assign(cab.cab_id)
        self._dropoff_paths[cab.cab_id] = dropoff_path
        self._ride_by_cab[cab.cab_id] = ride
        if ride in self.pending_rides:
            self.pending_rides.remove(ride)
        return True

    def _tick(self):
        if not self._running or self._game_over:
            return

        self._day_tick += 1
        money_changed = False

        if self._day_grace_remaining > 0:
            self._day_grace_remaining -= 1

        for cab in self.cabs:
            if cab.status == "resting":
                cab.rest_tick()
                self.cab_updated.emit(cab)
                continue
            if cab.status not in ("to_pickup", "en_route"):
                continue
            node = cab.tick()
            if node is not None:
                self.cab_nodes[cab.cab_id] = self.city_graph.to_node_id(node)
            self.cab_updated.emit(cab)
            if not cab.is_path_complete():
                continue
            prev_status = cab.status
            cab.complete_leg()
            if prev_status == "to_pickup":
                dropoff_path = self._dropoff_paths.get(cab.cab_id, [])
                if dropoff_path:
                    cab.assign_route(dropoff_path, "en_route")
            elif prev_status == "en_route":
                ride = self._ride_by_cab.get(cab.cab_id)
                if ride:
                    ride.complete()
                    self.money += ride.fare
                    self.day_earned += ride.fare
                    self.day_completed_rides += 1
                    self._run_total_earned += ride.fare
                    self._run_rides_completed += 1
                    money_changed = True
                    self._dropoff_paths.pop(cab.cab_id, None)
                    self._ride_by_cab.pop(cab.cab_id, None)
                    self.ride_completed.emit(ride)
                    self._check_day_complete()
            self.cab_updated.emit(cab)

        expired = []
        for ride in list(self.pending_rides):
            if ride.tick():
                expired.append(ride)
        for ride in expired:
            self.pending_rides = [r for r in self.pending_rides if r.ride_id != ride.ride_id]
            self._handle_missed_ride(ride)
            self.ride_expired.emit(ride)
            self._check_day_complete()

        if (
            self._day_grace_remaining <= 0
            and self._rides_spawned_today < self._rides_target_today
            and self._should_spawn(self._day_tick, len(self.cabs))
        ):
            ride = self._generate_ride()
            self.pending_rides.append(ride)
            self.all_rides.append(ride)
            self._rides_spawned_today += 1
            self.ride_spawned.emit(ride)

        if money_changed:
            self.money_changed.emit(self.money)

    def _check_day_complete(self):
        if self._rides_spawned_today < self._rides_target_today:
            return
        if self.pending_rides or self._ride_by_cab:
            return
        self._end_day()

    def _handle_missed_ride(self, ride):
        self.missed_rides_today += 1
        self._run_rides_missed += 1
        if self.missed_rides_today >= MAX_MISSED_PER_DAY:
            self._game_over = True
            self._timer.stop()
            self._finish_run("game_over")
            self.game_over.emit(f"You missed {MAX_MISSED_PER_DAY} rides in one day. Game over!")

    def add_cab(self):
        if self.money < CAB_COST:
            return False
        self.money -= CAB_COST
        cab = Cab(self._next_cab_id, driver_name())
        self._next_cab_id += 1
        self.cabs.append(cab)
        self.cab_nodes[cab.cab_id] = self.city_graph.random_node()
        self.fleet_updated.emit()
        self.money_changed.emit(self.money)
        return True

    def dispatch(self, ride_id, cab_id):
        ride = next((r for r in self.pending_rides if r.ride_id == ride_id), None)
        cab = next((c for c in self.cabs if c.cab_id == cab_id), None)
        cab_node = self.cab_nodes.get(cab_id)
        if ride is None or cab is None or cab_node is None:
            return False
        if self._assign_ride(ride, cab, cab_node):
            self.ride_assigned.emit(ride)
            self.cab_updated.emit(cab)
            return True
        return False

    def refuel_cab(self, cab_id):
        cab = next((c for c in self.cabs if c.cab_id == cab_id), None)
        if cab is None or self.money < REFUEL_COST:
            return False
        self.money -= REFUEL_COST
        cab.refuel()
        self.cab_updated.emit(cab)
        self.money_changed.emit(self.money)
        return True

    def rest_cab(self, cab_id):
        cab = next((c for c in self.cabs if c.cab_id == cab_id), None)
        if cab is None or cab.status != "idle":
            return False
        cab.force_rest()
        self.cab_updated.emit(cab)
        return True

    def buy_upgrade(self, cab_id, upgrade_type):
        cost = UPGRADE_COSTS.get(upgrade_type, 0)
        cab = next((c for c in self.cabs if c.cab_id == cab_id), None)
        if cab is None or self.money < cost:
            return False
        self.money -= cost
        cab.upgrade(upgrade_type)
        self.cab_updated.emit(cab)
        self.money_changed.emit(self.money)
        return True

    def get_ride_by_id(self, ride_id):
        for ride in self.all_rides:
            if ride.ride_id == ride_id:
                return ride
        for ride in self._ride_by_cab.values():
            if ride.ride_id == ride_id:
                return ride
        return None

    def get_ride_at_node(self, node_id):
        target = self.city_graph.to_node_id(node_id)
        for ride in self.pending_rides:
            if (
                self.city_graph.to_node_id(ride.pickup_node) == target
                or self.city_graph.to_node_id(ride.dropoff_node) == target
            ):
                return ride
        return None

    def get_assigned_rides(self):
        return list(self._ride_by_cab.values())

    def dispatch_preview(self, cab_id, ride_id):
        """Build dispatch panel text and whether dispatch is allowed."""
        if cab_id is None:
            return "Select an idle driver from the fleet or map.", False
        cab = next((c for c in self.cabs if c.cab_id == cab_id), None)
        if cab is None:
            return "Driver not found.", False
        if ride_id is None:
            if cab.status == "idle":
                return f"{cab.name} ready — select a Live order.", False
            return f"{cab.name} is {cab.status.replace('_', ' ')} — select an idle driver.", False

        ride = self.get_ride_by_id(ride_id)
        if ride is None or ride.outcome != "pending":
            return "Only Live orders can be dispatched.", False
        if cab.status != "idle":
            return f"{cab.name} is {cab.status.replace('_', ' ')} — pick an idle driver.", False

        cab_node = self.cab_nodes.get(cab_id)
        if cab_node is None:
            return f"{cab.name} position unknown.", False

        try:
            districts = route_label(self.city_graph, ride.pickup_node, ride.dropoff_node)
        except KeyError:
            districts = "Unknown route"

        pickup_path, pickup_m = self.pathfinder.distance_between(cab_node, ride.pickup_node)
        trip_m = ride.trip_meters or self.pathfinder.path_distance_meters(ride.route_path)
        secs = int(ride.ticks_remaining * TICK_MS / 1000)

        lines = [
            f"Driver: {cab.name} (idle)",
            f"Customer: {ride.passenger_name}",
            f"Class: {ride.ride_class_label}",
            f"Route: {districts}",
            f"To pickup: {self.pathfinder.format_distance(pickup_m)}",
            f"Trip: {self.pathfinder.format_distance(trip_m)}",
            f"Payout: ₾{ride.fare:.2f}  ·  Expires: {secs}s",
        ]
        if not pickup_path:
            lines.append("No route to pickup — cannot dispatch.")
            return "\n".join(lines), False
        lines.append("Ready to dispatch.")
        return "\n".join(lines), True

    def preview_distance(self, cab_id, node_id):
        cab = next((c for c in self.cabs if c.cab_id == cab_id), None)
        if cab is None:
            return {"path": [], "meters": 0.0, "text": "No cab selected."}
        current_node = self.cab_nodes.get(cab_id)
        if current_node is None:
            return {"path": [], "meters": 0.0, "text": "Cab position unknown."}
        target = self.city_graph.to_node_id(node_id)
        if not self.city_graph.has_node(target):
            return {"path": [], "meters": 0.0, "text": "Invalid map location."}
        path, meters = self.pathfinder.distance_between(current_node, target)
        ride = self.get_ride_at_node(target)
        target_label = "destination"
        if ride is not None:
            if self.city_graph.to_node_id(ride.dropoff_node) == target:
                target_label = f"dropoff ({ride.passenger_name})"
            elif self.city_graph.to_node_id(ride.pickup_node) == target:
                target_label = f"pickup ({ride.passenger_name})"
        text = f"{cab.name} → {target_label}\nDistance: {self.pathfinder.format_distance(meters)}"
        if ride and self.city_graph.to_node_id(ride.pickup_node) == target:
            text += "\nPress Dispatch when ready."
        return {"path": path, "meters": meters, "text": text, "ride": ride}

    def day_orders_progress(self):
        return self._rides_spawned_today, self._rides_target_today

    @property
    def is_order_free_period(self):
        return self._day_grace_remaining > 0

    def _finish_run(self, end_reason):
        if not self._run_id or self._run_finished:
            return
        finish_game_run(
            self._run_id,
            days_reached=self.day,
            days_completed=self._run_days_completed,
            total_earned=self._run_total_earned,
            final_money=self.money,
            rides_completed=self._run_rides_completed,
            rides_missed=self._run_rides_missed,
            fleet_size=len(self.cabs),
            end_reason=end_reason,
        )
        self._run_finished = True

    def stop(self):
        self._timer.stop()
        self._running = False
        if not self._run_finished:
            self._finish_run("quit")
