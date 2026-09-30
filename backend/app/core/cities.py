"""Small built-in gazetteer of Indian cities (approximate coordinates).

Used to (1) name a region, (2) label a clicked point ("12 km NE of Barasat"),
(3) pick the places that get storm-arrival clocks inside the current map box.
tier 1 = metro / state capital / major hub (used for region names).
"""
from __future__ import annotations

import math

# (name, lat, lon, tier)
CITIES: list[tuple[str, float, float, int]] = [
    ("Delhi", 28.61, 77.21, 1), ("Mumbai", 19.08, 72.88, 1), ("Kolkata", 22.57, 88.36, 1),
    ("Chennai", 13.08, 80.27, 1), ("Bengaluru", 12.97, 77.59, 1), ("Hyderabad", 17.39, 78.49, 1),
    ("Ahmedabad", 23.02, 72.57, 1), ("Pune", 18.52, 73.86, 1), ("Jaipur", 26.91, 75.79, 1),
    ("Lucknow", 26.85, 80.95, 1), ("Patna", 25.59, 85.14, 1), ("Bhopal", 23.26, 77.41, 1),
    ("Nagpur", 21.15, 79.09, 1), ("Guwahati", 26.14, 91.74, 1), ("Bhubaneswar", 20.30, 85.82, 1),
    ("Ranchi", 23.34, 85.31, 1), ("Raipur", 21.25, 81.63, 1), ("Chandigarh", 30.73, 76.78, 1),
    ("Dehradun", 30.32, 78.03, 1), ("Thiruvananthapuram", 8.52, 76.94, 1), ("Kochi", 9.93, 76.27, 1),
    ("Visakhapatnam", 17.69, 83.22, 1), ("Srinagar", 34.08, 74.80, 1), ("Indore", 22.72, 75.86, 1),
    ("Surat", 21.17, 72.83, 1), ("Coimbatore", 11.02, 76.96, 1), ("Amritsar", 31.63, 74.87, 1),
    ("Varanasi", 25.32, 83.01, 1), ("Agra", 27.18, 78.01, 1), ("Panaji", 15.50, 73.83, 1),
    ("Imphal", 24.82, 93.94, 1), ("Agartala", 23.83, 91.29, 1), ("Shillong", 25.57, 91.88, 1),
    ("Gangtok", 27.33, 88.61, 1), ("Shimla", 31.10, 77.17, 1), ("Jammu", 32.73, 74.87, 1),
    # West Bengal / east
    ("Howrah", 22.59, 88.26, 2), ("Barasat", 22.72, 88.48, 2), ("Krishnanagar", 23.40, 88.49, 2),
    ("Bardhaman", 23.23, 87.86, 2), ("Durgapur", 23.52, 87.31, 2), ("Asansol", 23.68, 86.98, 2),
    ("Kharagpur", 22.35, 87.32, 2), ("Haldia", 22.07, 88.07, 2), ("Siliguri", 26.72, 88.43, 2),
    ("Darjeeling", 27.04, 88.26, 2), ("Jamshedpur", 22.80, 86.20, 2), ("Dhanbad", 23.80, 86.43, 2),
    ("Cuttack", 20.46, 85.88, 2), ("Puri", 19.81, 85.83, 2), ("Gaya", 24.80, 85.00, 2),
    ("Muzaffarpur", 26.12, 85.39, 2), ("Bhagalpur", 25.24, 87.01, 2),
    # north
    ("Kanpur", 26.45, 80.35, 2), ("Prayagraj", 25.44, 81.85, 2), ("Gorakhpur", 26.76, 83.37, 2),
    ("Meerut", 28.98, 77.71, 2), ("Noida", 28.57, 77.32, 2), ("Gurugram", 28.46, 77.03, 2),
    ("Faridabad", 28.41, 77.31, 2), ("Ghaziabad", 28.67, 77.45, 2), ("Bareilly", 28.37, 79.43, 2),
    ("Moradabad", 28.84, 78.78, 2), ("Aligarh", 27.88, 78.08, 2), ("Ludhiana", 30.90, 75.86, 2),
    ("Ambala", 30.38, 76.78, 2), ("Rohtak", 28.90, 76.61, 2), ("Gwalior", 26.22, 78.18, 2),
    # west / central
    ("Vadodara", 22.31, 73.18, 2), ("Rajkot", 22.30, 70.80, 2), ("Nashik", 19.99, 73.79, 2),
    ("Thane", 19.22, 72.98, 2), ("Aurangabad", 19.88, 75.34, 2), ("Solapur", 17.66, 75.91, 2),
    ("Kolhapur", 16.70, 74.24, 2), ("Jabalpur", 23.18, 79.94, 2), ("Jodhpur", 26.24, 73.02, 2),
    ("Udaipur", 24.59, 73.71, 2), ("Kota", 25.21, 75.86, 2), ("Bikaner", 28.02, 73.31, 2),
    ("Ajmer", 26.45, 74.64, 2),
    # south
    ("Vijayawada", 16.51, 80.65, 2), ("Madurai", 9.93, 78.12, 2), ("Kozhikode", 11.26, 75.78, 2),
    ("Mysuru", 12.30, 76.64, 2), ("Mangaluru", 12.91, 74.86, 2), ("Warangal", 17.97, 79.59, 2),
    ("Tiruchirappalli", 10.79, 78.70, 2), ("Salem", 11.66, 78.15, 2), ("Vellore", 12.92, 79.13, 2),
    ("Puducherry", 11.93, 79.83, 2), ("Nellore", 14.44, 79.99, 2), ("Tirupati", 13.63, 79.42, 2),
    ("Belagavi", 15.85, 74.50, 2), ("Hubballi", 15.36, 75.12, 2),
]

# rough bounding box of India (lat_min, lat_max, lon_min, lon_max)
INDIA = (6.5, 37.1, 68.0, 97.6)
_DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def in_india(lat: float, lon: float) -> bool:
    return INDIA[0] <= lat <= INDIA[1] and INDIA[2] <= lon <= INDIA[3]


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = (lat2 - lat1) * 111.32
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    dy = lat2 - lat1
    dx = (lon2 - lon1) * math.cos(math.radians(lat1))
    return _DIRS[round((math.degrees(math.atan2(dx, dy)) + 360) % 360 / 45) % 8]


def nearest_city(lat: float, lon: float) -> dict:
    name, clat, clon, _ = min(CITIES, key=lambda c: _km(lat, lon, c[1], c[2]))
    return {"name": name, "distance_km": round(_km(lat, lon, clat, clon), 1),
            "bearing": _bearing(clat, clon, lat, lon)}   # direction of the point *from* the city


def region_name(lat: float, lon: float) -> str:
    majors = [c for c in CITIES if c[3] == 1 and _km(lat, lon, c[1], c[2]) <= 250]
    pool = majors or CITIES
    return min(pool, key=lambda c: _km(lat, lon, c[1], c[2]))[0] + " region"


def cities_in_bbox(bbox: tuple[float, float, float, float]) -> list[dict]:
    min_lon, min_lat, max_lon, max_lat = bbox
    return [{"name": n, "lat": la, "lon": lo} for n, la, lo, _ in CITIES
            if min_lat <= la <= max_lat and min_lon <= lo <= max_lon]