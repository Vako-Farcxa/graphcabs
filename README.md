# GraphCabs

Desktop taxi management game built with **Python** and **PyQt5**. You run a cab fleet on a real Tbilisi road network (OpenStreetMap via OSMnx), assign rides on a live Folium map, manage fuel and stamina, and grow your business day by day.

## Features

- Interactive map of Tbilisi (Folium + PyQtWebEngine)
- Real road graph routing (NetworkX / OSMnx)
- Ride spawning, dispatch, VIP fares, and day cycles
- Cab upgrades (fuel tank, stamina, speed)
- Local SQLite history of game runs

## Requirements

- Python 3.10+ recommended
- Windows, macOS, or Linux with a desktop GUI

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/Vako-Farcxa/graphcabs.git
cd YOUR_REPO

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the game
python -m graphcabs.main
```

First launch may take a moment while the map/graph loads from `graphcabs/assets/tbilisi_graph.graphml`.

## Project structure

```
graphcabs/
  main.py       # App entry point
  game.py       # Game loop, economy, dispatch
  window.py     # Main window
  map.py        # Folium map UI
  graph.py      # City graph & pathfinding
  db.py         # SQLite persistence
  config.py     # Game constants
  assets/       # Prebuilt Tbilisi GraphML
requirements.txt
```

## Dependencies

See `requirements.txt`: PyQt5, PyQtWebEngine, Folium, OSMnx, NetworkX, Faker.

## License

Add a license if you want others to reuse this code (e.g. MIT).
