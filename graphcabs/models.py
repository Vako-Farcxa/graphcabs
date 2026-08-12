"""Cab and ride entities."""

from graphcabs.config import (
    FUEL_DRAIN_PER_NODE,
    REST_TICKS,
    RIDE_EXPIRY_TICKS,
    TICKS_PER_NODE,
    TIREDNESS_PER_RIDE,
)


class Cab:
    def __init__(self, cab_id, name, fuel=100.0, tiredness=0.0):
        self.cab_id = cab_id
        self.name = name
        self.fuel = fuel
        self.tiredness = tiredness
        self.status = "idle"
        self.upgrade_levels = {"fuel_tank": 0, "stamina": 0, "speed": 0}
        self._path = []
        self._path_index = 0
        self._rest_ticks_remaining = 0
        self._move_cooldown = 0

    @property
    def max_fuel(self):
        return 100.0 + self.upgrade_levels["fuel_tank"] * 20

    @property
    def tiredness_threshold(self):
        return 80.0 + self.upgrade_levels["stamina"] * 10

    @property
    def rest_ticks_remaining(self):
        return self._rest_ticks_remaining

    def assign_route(self, path, next_status):
        self._path = list(path)
        self._path_index = 0
        self._move_cooldown = 0
        self.status = next_status

    def tick(self):
        if self.status == "resting" or not self._path or self._path_index >= len(self._path):
            return None
        if self._move_cooldown > 0:
            self._move_cooldown -= 1
            return None
        self._move_cooldown = max(1, TICKS_PER_NODE - self.upgrade_levels["speed"]) - 1
        node = self._path[self._path_index]
        self._path_index += 1
        self.fuel = max(0.0, self.fuel - FUEL_DRAIN_PER_NODE)
        if self.fuel <= 0:
            self.status = "out_of_fuel"
            return None
        return node

    def complete_leg(self):
        self._path = []
        self._path_index = 0
        if self.status == "to_pickup":
            return
        if self.status == "en_route":
            self.tiredness += TIREDNESS_PER_RIDE
            if self.tiredness < self.tiredness_threshold:
                self.status = "idle"
            else:
                self.status = "resting"
                self._rest_ticks_remaining = REST_TICKS

    def rest_tick(self):
        if self.status != "resting":
            return
        self._rest_ticks_remaining -= 1
        if self._rest_ticks_remaining <= 0:
            self.status = "idle"
            self.tiredness = 0.0

    def force_rest(self):
        self.status = "resting"
        self._rest_ticks_remaining = REST_TICKS
        self._path = []
        self._path_index = 0

    def refuel(self, amount=100.0):
        self.fuel = min(self.max_fuel, self.fuel + amount)
        if self.status == "out_of_fuel":
            self.status = "idle"

    def upgrade(self, upgrade_type):
        self.upgrade_levels[upgrade_type] = self.upgrade_levels.get(upgrade_type, 0) + 1
        if upgrade_type == "fuel_tank":
            self.fuel = min(self.max_fuel, self.fuel + 20.0)

    def is_path_complete(self):
        return bool(self._path) and self._path_index >= len(self._path)

    @property
    def active_path(self):
        return list(self._path)

    @property
    def path_index(self):
        return self._path_index

    def display_position(self):
        if not self._path:
            return None, 0.0
        if self._path_index <= 0:
            return self._path[0], 0.0
        if self._path_index >= len(self._path):
            return self._path[-1], 0.0
        return self._path[self._path_index - 1], 0.5


class Ride:
    def __init__(self, ride_id, pickup_node, dropoff_node, fare, day, route_path=None,
                 ride_class="basic", passenger_name=""):
        self.ride_id = ride_id
        self.pickup_node = int(pickup_node)
        self.dropoff_node = int(dropoff_node)
        self.fare = fare
        self.day = day
        self.route_path = [int(n) for n in route_path] if route_path else []
        self.ride_class = ride_class if ride_class in ("basic", "vip") else "basic"
        self.passenger_name = passenger_name
        self.trip_meters = 0.0
        self.outcome = "pending"
        self.ticks_remaining = RIDE_EXPIRY_TICKS
        self.assigned_cab_id = None

    @property
    def ride_class_label(self):
        return "VIP" if self.ride_class == "vip" else "Basic"

    def tick(self):
        if self.outcome != "pending":
            return False
        self.ticks_remaining -= 1
        if self.ticks_remaining <= 0:
            self.outcome = "missed"
            return True
        return False

    def assign(self, cab_id):
        self.outcome = "assigned"
        self.assigned_cab_id = cab_id

    def complete(self):
        self.outcome = "completed"
