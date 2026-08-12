"""Georgian driver and passenger names via Faker."""

from faker import Faker

_fake = Faker("ka_GE")
_used_drivers = set()


def driver_name():
    for _ in range(40):
        name = _fake.name()
        if name not in _used_drivers:
            _used_drivers.add(name)
            return name
    name = f"{_fake.first_name()} {_fake.last_name()}"
    _used_drivers.add(name)
    return name


def passenger_name():
    return _fake.name()
