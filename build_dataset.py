"""Builds data/cars_india.csv and frontend/cars-data.js from a hand-curated catalogue of the Indian new-car market.

    python build_dataset.py

Every model below is a car that is actually sold in India (mass market through to supercars), with realistic
engines, fuel types, gearboxes, seating, efficiency and approximate ex-showroom prices (INR lakh, 2025).
Each (model, fuel, gearbox) combination is expanded into three trims (base / mid / top) so the price
range of a model is represented. Prices are indicative and change often - verify before buying.

Variant tuple: (fuel, gearboxes, engine_cc, efficiency, power_bhp, price_lo_lakh, price_hi_lakh)
  gearboxes: "M" manual only, "A" automatic only, "MA" both
  efficiency: km/l (Petrol, Diesel, Hybrid), km/kg (CNG), or claimed range in km (Electric)
  engine_cc is 0 for electric cars.
"""
import csv
import json
import zlib
from pathlib import Path

BASE = Path(__file__).resolve().parent

P, D, C, E, H = "Petrol", "Diesel", "CNG", "Electric", "Hybrid"

# brand -> list of (model, body, seats, model_year, [variants])
CATALOG = {
    "Maruti Suzuki": [
        ("Alto K10", "Hatchback", 5, 2022, [(P, "MA", 998, 24.4, 66, 4.2, 6.1), (C, "M", 998, 33.4, 56, 5.9, 6.2)]),
        ("S-Presso", "Hatchback", 5, 2022, [(P, "MA", 998, 24.8, 66, 4.3, 6.1), (C, "M", 998, 32.7, 56, 5.9, 6.2)]),
        ("Wagon R", "Hatchback", 5, 2022, [(P, "MA", 1197, 24.4, 89, 5.5, 7.3), (C, "M", 998, 34.0, 56, 6.4, 6.9)]),
        ("Celerio", "Hatchback", 5, 2021, [(P, "MA", 998, 25.2, 66, 5.6, 7.2), (C, "M", 998, 34.4, 56, 6.7, 7.0)]),
        ("Ignis", "Hatchback", 5, 2020, [(P, "MA", 1197, 20.9, 81, 5.9, 8.3)]),
        ("Swift", "Hatchback", 5, 2024, [(P, "MA", 1197, 24.8, 81, 6.5, 9.6), (C, "M", 1197, 32.8, 69, 8.2, 9.2)]),
        ("Baleno", "Hatchback", 5, 2022, [(P, "MA", 1197, 22.9, 88, 6.7, 9.9), (C, "M", 1197, 30.6, 76, 8.3, 9.2)]),
        ("Dzire", "Sedan", 5, 2024, [(P, "MA", 1197, 24.8, 81, 6.8, 10.1), (C, "M", 1197, 33.7, 69, 8.8, 9.8)]),
        ("Fronx", "SUV", 5, 2023, [(P, "MA", 1197, 21.8, 88, 7.5, 12.0), (P, "MA", 998, 21.5, 99, 9.5, 13.1), (C, "M", 1197, 28.5, 76, 8.5, 9.1)]),
        ("Brezza", "SUV", 5, 2022, [(P, "MA", 1462, 20.2, 102, 8.3, 14.1), (C, "M", 1462, 25.5, 87, 9.3, 12.1)]),
        ("Grand Vitara", "SUV", 5, 2022, [(P, "MA", 1462, 21.1, 102, 11.0, 19.5), (H, "A", 1490, 27.9, 114, 17.0, 20.0)]),
        ("Jimny", "SUV", 4, 2023, [(P, "MA", 1462, 16.9, 103, 12.7, 14.8)]),
        ("Eeco", "MPV", 7, 2022, [(P, "M", 1196, 19.7, 80, 5.3, 6.5), (C, "M", 1196, 26.8, 70, 6.3, 6.8)]),
        ("Ertiga", "MPV", 7, 2022, [(P, "MA", 1462, 20.5, 102, 8.8, 13.0), (C, "M", 1462, 26.1, 87, 10.7, 12.1)]),
        ("XL6", "MPV", 6, 2022, [(P, "MA", 1462, 20.9, 102, 11.6, 14.8)]),
        ("Invicto", "MPV", 7, 2023, [(H, "A", 1987, 23.2, 150, 25.0, 29.0)]),
    ],
    "Hyundai": [
        ("Grand i10 Nios", "Hatchback", 5, 2023, [(P, "MA", 1197, 20.7, 82, 5.9, 8.7), (C, "M", 1197, 27.0, 69, 7.7, 8.5)]),
        ("i20", "Hatchback", 5, 2023, [(P, "MA", 1197, 20.0, 83, 7.0, 11.2), (P, "MA", 998, 20.0, 118, 9.9, 12.2)]),
        ("Aura", "Sedan", 5, 2023, [(P, "MA", 1197, 20.5, 82, 6.5, 9.3), (C, "M", 1197, 28.0, 69, 8.0, 8.9)]),
        ("Exter", "SUV", 5, 2023, [(P, "MA", 1197, 19.4, 82, 6.1, 10.4), (C, "M", 1197, 27.1, 69, 8.5, 9.6)]),
        ("Venue", "SUV", 5, 2022, [(P, "MA", 1197, 17.5, 82, 7.9, 11.7), (P, "MA", 998, 18.0, 118, 12.0, 13.5), (D, "MA", 1493, 23.4, 114, 10.0, 13.5)]),
        ("Verna", "Sedan", 5, 2023, [(P, "MA", 1497, 18.6, 113, 11.0, 17.5), (P, "A", 1482, 20.0, 158, 15.8, 18.0)]),
        ("Creta", "SUV", 5, 2024, [(P, "MA", 1497, 17.4, 113, 11.1, 20.2), (D, "MA", 1493, 21.8, 114, 12.5, 20.2), (P, "A", 1482, 18.4, 158, 17.3, 20.2)]),
        ("Alcazar", "SUV", 7, 2024, [(P, "MA", 1482, 18.0, 158, 15.0, 21.5), (D, "MA", 1493, 20.4, 114, 15.5, 21.1)]),
        ("Tucson", "SUV", 5, 2022, [(P, "A", 1999, 13.0, 154, 29.3, 32.0), (D, "A", 1997, 18.0, 184, 32.0, 35.5)]),
        ("Creta Electric", "SUV", 5, 2025, [(E, "A", 0, 473, 169, 17.9, 24.4)]),
        ("Ioniq 5", "SUV", 5, 2022, [(E, "A", 0, 631, 214, 46.0, 46.3)]),
    ],
    "Kia": [
        ("Sonet", "SUV", 5, 2024, [(P, "MA", 1197, 18.4, 82, 8.0, 11.8), (P, "MA", 998, 18.3, 118, 10.0, 14.7), (D, "MA", 1493, 22.3, 114, 9.7, 15.7)]),
        ("Seltos", "SUV", 5, 2023, [(P, "MA", 1497, 17.0, 113, 11.1, 20.0), (D, "MA", 1493, 20.7, 114, 12.5, 20.0), (P, "A", 1482, 17.7, 158, 16.0, 20.5)]),
        ("Carens", "MPV", 7, 2022, [(P, "MA", 1497, 16.5, 113, 10.5, 19.0), (D, "MA", 1493, 21.0, 114, 12.0, 19.0), (P, "A", 1482, 16.7, 158, 18.0, 19.8)]),
        ("Carnival", "MPV", 7, 2024, [(D, "A", 2151, 14.8, 190, 63.9, 65.0)]),
        ("EV6", "SUV", 5, 2022, [(E, "A", 0, 708, 321, 60.9, 65.9)]),
        ("EV9", "SUV", 7, 2024, [(E, "A", 0, 561, 379, 129.0, 131.0)]),
    ],
    "Tata Motors": [
        ("Tiago", "Hatchback", 5, 2023, [(P, "MA", 1199, 19.0, 84, 5.0, 8.4), (C, "MA", 1199, 26.5, 72, 6.6, 8.2)]),
        ("Tiago EV", "Hatchback", 5, 2022, [(E, "A", 0, 315, 74, 7.99, 11.9)]),
        ("Tigor", "Sedan", 5, 2022, [(P, "MA", 1199, 19.3, 84, 5.5, 8.9), (C, "MA", 1199, 26.4, 72, 7.5, 9.5)]),
        ("Altroz", "Hatchback", 5, 2023, [(P, "MA", 1199, 19.3, 87, 6.7, 11.3), (D, "M", 1497, 23.6, 89, 8.6, 11.3), (C, "MA", 1199, 26.2, 72, 7.6, 10.6)]),
        ("Punch", "SUV", 5, 2024, [(P, "MA", 1199, 20.1, 86, 6.1, 10.3), (C, "MA", 1199, 27.0, 72, 7.2, 9.9)]),
        ("Punch EV", "SUV", 5, 2024, [(E, "A", 0, 421, 120, 9.9, 14.4)]),
        ("Nexon", "SUV", 5, 2023, [(P, "MA", 1199, 17.4, 120, 8.0, 15.6), (D, "MA", 1497, 23.2, 113, 10.0, 15.8), (C, "MA", 1199, 24.0, 99, 8.9, 14.6)]),
        ("Nexon EV", "SUV", 5, 2023, [(E, "A", 0, 489, 143, 12.5, 17.2)]),
        ("Curvv", "SUV", 5, 2024, [(P, "MA", 1199, 16.5, 120, 9.9, 17.2), (D, "MA", 1497, 19.5, 113, 11.5, 18.5)]),
        ("Curvv EV", "SUV", 5, 2024, [(E, "A", 0, 502, 165, 17.5, 22.0)]),
        ("Harrier", "SUV", 5, 2023, [(D, "MA", 1956, 16.8, 167, 15.0, 26.5)]),
        ("Safari", "SUV", 7, 2023, [(D, "MA", 1956, 16.3, 167, 15.5, 27.3)]),
    ],
    "Mahindra": [
        ("Bolero", "SUV", 7, 2022, [(D, "M", 1493, 16.0, 75, 9.8, 10.8)]),
        ("Bolero Neo", "SUV", 7, 2022, [(D, "M", 1493, 17.3, 100, 9.9, 12.2)]),
        ("Thar", "SUV", 4, 2024, [(P, "MA", 1997, 15.2, 150, 11.5, 17.6), (D, "MA", 2184, 15.2, 117, 11.5, 17.6)]),
        ("Thar Roxx", "SUV", 5, 2024, [(P, "MA", 1997, 12.4, 160, 12.99, 23.0), (D, "MA", 2184, 15.4, 172, 13.99, 23.0)]),
        ("XUV 3XO", "SUV", 5, 2024, [(P, "MA", 1197, 18.9, 110, 7.5, 15.5), (D, "MA", 1498, 20.6, 115, 9.9, 15.5)]),
        ("Scorpio Classic", "SUV", 7, 2022, [(D, "M", 2184, 14.4, 130, 13.6, 17.4)]),
        ("Scorpio-N", "SUV", 7, 2022, [(P, "MA", 1997, 12.0, 200, 13.8, 24.5), (D, "MA", 2198, 15.4, 172, 14.0, 24.9)]),
        ("XUV700", "SUV", 7, 2022, [(P, "MA", 1999, 12.4, 197, 14.0, 25.0), (D, "MA", 2184, 16.0, 182, 14.0, 25.6)]),
        ("BE 6", "SUV", 5, 2025, [(E, "A", 0, 535, 281, 18.9, 27.0)]),
        ("XEV 9e", "SUV", 5, 2025, [(E, "A", 0, 542, 282, 21.9, 31.0)]),
    ],
    "Toyota": [
        ("Glanza", "Hatchback", 5, 2022, [(P, "MA", 1197, 22.9, 88, 6.9, 10.0), (C, "M", 1197, 30.6, 76, 8.3, 9.2)]),
        ("Urban Cruiser Taisor", "SUV", 5, 2024, [(P, "MA", 1197, 21.7, 88, 7.7, 13.0), (C, "M", 1197, 28.5, 76, 9.7, 10.5)]),
        ("Urban Cruiser Hyryder", "SUV", 5, 2022, [(P, "MA", 1462, 21.1, 102, 11.1, 19.0), (H, "A", 1490, 27.9, 114, 15.0, 20.0), (C, "M", 1462, 26.6, 87, 13.0, 15.0)]),
        ("Rumion", "MPV", 7, 2023, [(P, "MA", 1462, 20.5, 102, 10.4, 13.7), (C, "M", 1462, 26.1, 87, 11.8, 12.7)]),
        ("Innova Crysta", "MPV", 7, 2022, [(D, "MA", 2393, 15.0, 150, 19.99, 26.3)]),
        ("Innova Hycross", "MPV", 7, 2023, [(H, "A", 1987, 23.2, 183, 19.9, 30.9), (P, "A", 1987, 16.1, 172, 19.9, 21.5)]),
        ("Fortuner", "SUV", 7, 2022, [(D, "MA", 2755, 14.4, 201, 33.7, 46.3), (P, "MA", 2694, 10.0, 164, 33.4, 36.3)]),
        ("Camry", "Sedan", 5, 2024, [(H, "A", 2487, 23.2, 218, 48.0, 48.5)]),
        ("Vellfire", "MPV", 7, 2023, [(H, "A", 2487, 16.4, 190, 122.0, 123.0)]),
        ("Land Cruiser 300", "SUV", 7, 2022, [(D, "A", 3346, 10.0, 304, 210.0, 232.0)]),
    ],
    "Honda": [
        ("Amaze", "Sedan", 5, 2024, [(P, "MA", 1199, 18.7, 89, 8.0, 10.9)]),
        ("City", "Sedan", 5, 2023, [(P, "MA", 1498, 17.8, 119, 11.8, 16.4), (H, "A", 1498, 27.1, 126, 19.0, 20.6)]),
        ("Elevate", "SUV", 5, 2023, [(P, "MA", 1498, 15.3, 119, 11.9, 16.9)]),
    ],
    "Renault": [
        ("Kwid", "Hatchback", 5, 2022, [(P, "MA", 999, 21.5, 67, 4.7, 6.4)]),
        ("Triber", "MPV", 7, 2022, [(P, "MA", 999, 20.0, 71, 6.1, 8.8)]),
        ("Kiger", "SUV", 5, 2022, [(P, "MA", 999, 19.2, 71, 6.0, 11.2), (P, "MA", 999, 17.9, 98, 9.7, 11.2)]),
    ],
    "Nissan": [
        ("Magnite", "SUV", 5, 2024, [(P, "MA", 999, 19.9, 71, 6.1, 11.2), (P, "MA", 999, 17.9, 99, 9.5, 11.2)]),
    ],
    "Skoda": [
        ("Kylaq", "SUV", 5, 2025, [(P, "MA", 999, 19.7, 114, 7.9, 14.4)]),
        ("Slavia", "Sedan", 5, 2022, [(P, "MA", 999, 19.4, 114, 10.7, 19.1), (P, "MA", 1498, 18.1, 148, 15.9, 19.1)]),
        ("Kushaq", "SUV", 5, 2021, [(P, "MA", 999, 19.8, 114, 10.9, 18.3), (P, "MA", 1498, 18.1, 148, 16.0, 19.0)]),
        ("Kodiaq", "SUV", 7, 2025, [(P, "A", 1984, 12.0, 187, 39.99, 46.0)]),
        ("Superb", "Sedan", 5, 2024, [(P, "A", 1984, 14.0, 187, 54.0, 56.0)]),
    ],
    "Volkswagen": [
        ("Virtus", "Sedan", 5, 2022, [(P, "MA", 999, 19.4, 114, 11.6, 19.4), (P, "MA", 1498, 18.1, 148, 15.5, 19.4)]),
        ("Taigun", "SUV", 5, 2021, [(P, "MA", 999, 19.2, 114, 11.7, 19.7), (P, "MA", 1498, 18.2, 148, 16.0, 19.7)]),
        ("Tiguan", "SUV", 5, 2025, [(P, "A", 1984, 12.6, 187, 49.0, 50.0)]),
        ("Golf GTI", "Hatchback", 5, 2025, [(P, "A", 1984, 12.0, 261, 52.0, 53.0)]),
    ],
    "MG": [
        ("Comet EV", "Hatchback", 4, 2023, [(E, "A", 0, 230, 41, 7.0, 10.0)]),
        ("Astor", "SUV", 5, 2021, [(P, "MA", 1498, 14.8, 108, 10.0, 17.5)]),
        ("Hector", "SUV", 5, 2023, [(P, "MA", 1451, 14.0, 141, 14.0, 22.5), (D, "M", 1956, 16.5, 167, 17.0, 22.5)]),
        ("Hector Plus", "SUV", 7, 2023, [(P, "MA", 1451, 14.0, 141, 17.5, 23.0), (D, "M", 1956, 16.5, 167, 18.7, 23.0)]),
        ("Windsor EV", "MPV", 5, 2024, [(E, "A", 0, 332, 134, 13.99, 16.0)]),
        ("ZS EV", "SUV", 5, 2022, [(E, "A", 0, 461, 174, 19.0, 25.4)]),
        ("Gloster", "SUV", 7, 2020, [(D, "MA", 1996, 12.0, 215, 39.6, 44.0)]),
        ("Cyberster", "Coupe", 2, 2025, [(E, "A", 0, 580, 510, 75.0, 77.0)]),
    ],
    "Jeep": [
        ("Compass", "SUV", 5, 2022, [(D, "MA", 1956, 14.9, 168, 19.0, 32.0)]),
        ("Meridian", "SUV", 7, 2022, [(D, "MA", 1956, 14.0, 168, 25.0, 38.7)]),
        ("Wrangler", "SUV", 4, 2021, [(P, "A", 1995, 10.6, 268, 67.7, 71.0)]),
    ],
    "Citroen": [
        ("C3", "Hatchback", 5, 2022, [(P, "M", 1198, 19.8, 82, 6.2, 8.5), (P, "MA", 1199, 19.4, 108, 8.9, 12.8)]),
        ("eC3", "Hatchback", 5, 2023, [(E, "A", 0, 320, 56, 12.8, 13.7)]),
        ("Basalt", "SUV", 5, 2024, [(P, "MA", 1199, 18.9, 108, 8.0, 14.1)]),
        ("C3 Aircross", "SUV", 5, 2023, [(P, "MA", 1199, 18.5, 108, 10.0, 17.5)]),
    ],
    "BYD": [
        ("Atto 3", "SUV", 5, 2022, [(E, "A", 0, 521, 201, 24.99, 34.0)]),
        ("Seal", "Sedan", 5, 2024, [(E, "A", 0, 650, 308, 41.0, 53.0)]),
        ("Sealion 7", "SUV", 5, 2025, [(E, "A", 0, 567, 308, 48.9, 54.9)]),
        ("eMax 7", "MPV", 7, 2022, [(E, "A", 0, 530, 161, 26.9, 29.5)]),
    ],
    # ------------------------------------------------------------------ luxury
    "Mercedes-Benz": [
        ("GLA", "SUV", 5, 2021, [(P, "A", 1332, 14.2, 161, 50.5, 54.0), (D, "A", 1950, 17.4, 187, 56.0, 58.0)]),
        ("EQA", "SUV", 5, 2024, [(E, "A", 0, 560, 188, 67.0, 68.0)]),
        ("C-Class", "Sedan", 5, 2022, [(P, "A", 1496, 16.0, 201, 59.9, 62.0), (D, "A", 1993, 20.0, 197, 65.0, 67.0)]),
        ("E-Class", "Sedan", 5, 2024, [(P, "A", 1999, 14.0, 201, 77.0, 80.0), (D, "A", 1993, 18.0, 194, 81.0, 84.0)]),
        ("S-Class", "Sedan", 5, 2021, [(P, "A", 2999, 11.0, 362, 188.0, 192.0), (D, "A", 2925, 14.0, 286, 190.0, 195.0)]),
        ("GLC", "SUV", 5, 2023, [(P, "A", 1999, 12.0, 254, 76.8, 78.0), (D, "A", 1993, 16.0, 197, 76.5, 78.5)]),
        ("GLE", "SUV", 5, 2023, [(D, "A", 1993, 12.0, 265, 97.9, 101.0), (P, "A", 2999, 10.0, 375, 112.0, 118.0)]),
        ("GLS", "SUV", 7, 2023, [(D, "A", 2925, 11.0, 362, 134.0, 139.0)]),
        ("G-Class", "SUV", 5, 2022, [(D, "A", 2925, 10.0, 326, 255.0, 262.0), (P, "A", 3982, 7.0, 585, 360.0, 365.0)]),
        ("Maybach S-Class", "Sedan", 4, 2022, [(P, "A", 3982, 9.0, 496, 270.0, 280.0)]),
        ("Maybach GLS", "SUV", 4, 2023, [(P, "A", 3982, 8.0, 550, 330.0, 340.0)]),
        ("EQB", "MPV", 7, 2023, [(E, "A", 0, 423, 288, 72.9, 77.5)]),
        ("EQE SUV", "SUV", 5, 2023, [(E, "A", 0, 550, 402, 139.0, 142.0)]),
        ("EQS SUV", "SUV", 7, 2023, [(E, "A", 0, 809, 544, 141.0, 148.0)]),
        ("EQS Sedan", "Sedan", 5, 2022, [(E, "A", 0, 857, 516, 162.0, 165.0)]),
        ("AMG GT 63", "Coupe", 4, 2024, [(P, "A", 3982, 8.0, 630, 330.0, 335.0)]),
    ],
    "BMW": [
        ("2 Series Gran Coupe", "Sedan", 5, 2022, [(P, "A", 1998, 15.0, 189, 43.9, 46.9)]),
        ("3 Series Gran Limousine", "Sedan", 5, 2023, [(P, "A", 1998, 14.0, 255, 60.6, 62.0), (D, "A", 1995, 18.7, 188, 59.9, 61.0)]),
        ("5 Series", "Sedan", 5, 2024, [(P, "A", 1998, 14.0, 255, 72.9, 75.0), (D, "A", 1995, 19.0, 190, 76.5, 78.0)]),
        ("7 Series", "Sedan", 5, 2023, [(P, "A", 2998, 11.0, 380, 180.0, 185.0), (D, "A", 2993, 14.0, 281, 184.0, 188.0)]),
        ("i7", "Sedan", 5, 2023, [(E, "A", 0, 625, 536, 203.0, 212.0)]),
        ("i4", "Sedan", 5, 2022, [(E, "A", 0, 590, 335, 72.5, 77.5)]),
        ("X1", "SUV", 5, 2023, [(P, "A", 1499, 15.0, 134, 49.5, 52.0), (D, "A", 1995, 19.0, 148, 50.5, 53.0)]),
        ("iX1", "SUV", 5, 2023, [(E, "A", 0, 531, 313, 49.0, 52.0)]),
        ("X3", "SUV", 5, 2025, [(P, "A", 1998, 13.0, 249, 75.8, 78.0), (D, "A", 1995, 17.0, 194, 77.0, 79.0)]),
        ("X5", "SUV", 5, 2023, [(P, "A", 2998, 11.0, 335, 97.9, 102.0), (D, "A", 2993, 14.0, 281, 98.0, 102.0)]),
        ("X7", "SUV", 7, 2023, [(P, "A", 2998, 10.0, 375, 127.0, 131.0), (D, "A", 2993, 13.0, 347, 125.0, 130.0)]),
        ("iX", "SUV", 5, 2022, [(E, "A", 0, 575, 516, 140.0, 142.0)]),
        ("XM", "SUV", 5, 2023, [(H, "A", 4395, 12.0, 644, 260.0, 265.0)]),
        ("Z4", "Coupe", 2, 2023, [(P, "A", 1998, 14.0, 255, 90.0, 92.0)]),
        ("M4 Competition", "Coupe", 4, 2023, [(P, "A", 2993, 10.0, 503, 153.0, 158.0)]),
    ],
    "Audi": [
        ("Q3", "SUV", 5, 2023, [(P, "A", 1984, 14.0, 187, 44.99, 54.0)]),
        ("A6", "Sedan", 5, 2024, [(P, "A", 1984, 14.0, 241, 65.7, 68.0)]),
        ("Q5", "SUV", 5, 2023, [(P, "A", 1984, 13.0, 245, 66.99, 72.0)]),
        ("Q7", "SUV", 7, 2022, [(P, "A", 2995, 11.0, 340, 88.0, 98.0)]),
        ("Q8", "SUV", 5, 2023, [(P, "A", 2995, 11.0, 340, 117.0, 122.0)]),
        ("A8 L", "Sedan", 5, 2022, [(P, "A", 2995, 11.0, 335, 177.0, 180.0)]),
        ("Q8 e-tron", "SUV", 5, 2024, [(E, "A", 0, 600, 402, 114.0, 128.0)]),
        ("e-tron GT", "Sedan", 4, 2022, [(E, "A", 0, 500, 523, 172.0, 195.0)]),
        ("RS Q8", "SUV", 5, 2023, [(P, "A", 3996, 8.0, 592, 249.0, 255.0)]),
        ("RS 5 Sportback", "Sedan", 5, 2023, [(P, "A", 2894, 9.0, 444, 113.0, 118.0)]),
    ],
    "Volvo": [
        ("EX30", "SUV", 5, 2025, [(E, "A", 0, 480, 268, 39.99, 41.0)]),
        ("XC40 Recharge", "SUV", 5, 2022, [(E, "A", 0, 418, 408, 56.1, 57.0)]),
        ("S90", "Sedan", 5, 2022, [(H, "A", 1969, 15.0, 247, 68.0, 72.0)]),
        ("XC60", "SUV", 5, 2022, [(H, "A", 1969, 14.0, 247, 68.9, 72.0)]),
        ("XC90", "SUV", 7, 2022, [(H, "A", 1969, 12.0, 247, 102.0, 104.0)]),
        ("EX90", "SUV", 7, 2025, [(E, "A", 0, 600, 517, 119.0, 122.0)]),
    ],
    "Jaguar": [
        ("F-Pace", "SUV", 5, 2022, [(P, "A", 1997, 12.0, 247, 72.9, 76.0)]),
        ("I-Pace", "SUV", 5, 2021, [(E, "A", 0, 470, 395, 120.0, 126.0)]),
    ],
    "Land Rover": [
        ("Discovery Sport", "SUV", 7, 2022, [(D, "A", 1997, 14.0, 201, 64.0, 69.0)]),
        ("Range Rover Evoque", "SUV", 5, 2022, [(D, "A", 1997, 14.0, 201, 67.9, 72.0), (P, "A", 1997, 11.0, 247, 69.0, 73.0)]),
        ("Range Rover Velar", "SUV", 5, 2022, [(D, "A", 1997, 14.0, 201, 87.9, 92.0), (P, "A", 1997, 11.0, 247, 87.0, 93.0)]),
        ("Defender", "SUV", 5, 2022, [(D, "A", 2997, 11.0, 296, 105.0, 150.0), (P, "A", 1997, 9.0, 296, 104.0, 148.0)]),
        ("Range Rover Sport", "SUV", 5, 2023, [(D, "A", 2997, 10.0, 346, 164.0, 190.0), (P, "A", 4395, 7.0, 523, 190.0, 240.0)]),
        ("Range Rover", "SUV", 5, 2022, [(D, "A", 2997, 10.0, 346, 236.0, 310.0), (P, "A", 4395, 7.0, 523, 374.0, 498.0)]),
    ],
    "Lexus": [
        ("ES 300h", "Sedan", 5, 2022, [(H, "A", 2487, 22.0, 215, 64.9, 69.7)]),
        ("NX 350h", "SUV", 5, 2022, [(H, "A", 2487, 17.0, 240, 68.0, 71.0)]),
        ("RX 350h", "SUV", 5, 2023, [(H, "A", 2487, 16.0, 240, 95.8, 100.0)]),
        ("LM 350h", "MPV", 4, 2024, [(H, "A", 2487, 15.0, 245, 200.0, 250.0)]),
        ("LX 500d", "SUV", 7, 2022, [(D, "A", 3346, 8.0, 304, 282.0, 300.0)]),
    ],
    "Porsche": [
        ("Macan", "SUV", 5, 2022, [(P, "A", 1984, 11.0, 261, 88.0, 100.0)]),
        ("Macan Electric", "SUV", 5, 2024, [(E, "A", 0, 591, 402, 165.0, 190.0)]),
        ("Cayenne", "SUV", 5, 2023, [(P, "A", 2995, 10.0, 349, 136.0, 190.0)]),
        ("718 Cayman", "Coupe", 2, 2022, [(P, "A", 1988, 10.0, 295, 125.0, 150.0)]),
        ("Panamera", "Sedan", 4, 2024, [(P, "A", 2894, 10.0, 348, 170.0, 200.0)]),
        ("Taycan", "Sedan", 4, 2022, [(E, "A", 0, 484, 402, 170.0, 230.0)]),
        ("911", "Coupe", 4, 2023, [(P, "A", 2981, 9.0, 379, 199.0, 370.0)]),
    ],
    "MINI": [
        ("Cooper", "Hatchback", 4, 2022, [(P, "A", 1998, 15.0, 175, 44.9, 48.0)]),
        ("Cooper SE", "Hatchback", 4, 2023, [(E, "A", 0, 270, 181, 53.9, 54.9)]),
        ("Countryman Electric", "SUV", 5, 2024, [(E, "A", 0, 462, 201, 54.9, 66.0)]),
    ],
    "Rolls-Royce": [
        ("Ghost", "Sedan", 5, 2021, [(P, "A", 6749, 6.0, 563, 895.0, 1050.0)]),
        ("Phantom", "Sedan", 5, 2023, [(P, "A", 6749, 6.0, 563, 950.0, 1100.0)]),
        ("Cullinan", "SUV", 5, 2023, [(P, "A", 6749, 6.0, 563, 1050.0, 1250.0)]),
        ("Spectre", "Coupe", 4, 2023, [(E, "A", 0, 530, 576, 750.0, 800.0)]),
    ],
    "Bentley": [
        ("Continental GT", "Coupe", 4, 2023, [(P, "A", 3996, 8.0, 542, 500.0, 560.0)]),
        ("Flying Spur", "Sedan", 5, 2023, [(P, "A", 3996, 8.0, 542, 500.0, 570.0)]),
        ("Bentayga", "SUV", 5, 2023, [(P, "A", 3996, 7.0, 542, 500.0, 600.0)]),
    ],
    "Lamborghini": [
        ("Urus", "SUV", 5, 2023, [(P, "A", 3996, 7.0, 657, 418.0, 460.0)]),
        ("Huracan", "Coupe", 2, 2023, [(P, "A", 5204, 6.0, 631, 404.0, 440.0)]),
        ("Revuelto", "Coupe", 2, 2024, [(H, "A", 6498, 5.0, 1001, 889.0, 900.0)]),
    ],
    "Ferrari": [
        ("Roma", "Coupe", 4, 2022, [(P, "A", 3855, 8.0, 612, 376.0, 400.0)]),
        ("296 GTB", "Coupe", 2, 2023, [(H, "A", 2992, 10.0, 818, 540.0, 560.0)]),
        ("SF90 Stradale", "Coupe", 2, 2022, [(H, "A", 3990, 7.0, 986, 750.0, 780.0)]),
        ("12Cilindri", "Coupe", 2, 2024, [(P, "A", 6496, 6.0, 819, 890.0, 910.0)]),
        ("Purosangue", "SUV", 4, 2023, [(P, "A", 6496, 5.0, 715, 1050.0, 1100.0)]),
    ],
    "Maserati": [
        ("Grecale", "SUV", 5, 2023, [(P, "A", 1995, 9.0, 296, 131.0, 150.0)]),
        ("GranTurismo", "Coupe", 4, 2023, [(P, "A", 2992, 8.0, 483, 272.0, 290.0)]),
        ("MC20", "Coupe", 2, 2022, [(P, "A", 2992, 7.0, 630, 369.0, 380.0)]),
    ],
    "Aston Martin": [
        ("Vantage", "Coupe", 2, 2024, [(P, "A", 3982, 8.0, 656, 399.0, 410.0)]),
        ("DB12", "Coupe", 4, 2023, [(P, "A", 3982, 8.0, 671, 459.0, 470.0)]),
        ("DBX707", "SUV", 5, 2022, [(P, "A", 3982, 6.0, 697, 463.0, 475.0)]),
    ],
}

LUXURY_BRANDS = ["Mercedes-Benz", "BMW", "Audi", "Volvo", "Jaguar", "Land Rover", "Lexus", "Porsche", "MINI",
                 "Rolls-Royce", "Bentley", "Lamborghini", "Ferrari", "Maserati", "Aston Martin"]

# Approximate fuel prices (INR) used to turn mileage into a running cost per km.
FUEL_PRICE = {"Petrol": 100.0, "Diesel": 90.0, "CNG": 85.0, "Hybrid": 100.0}
EV_COST_PER_KM = 1.2          # ~ Rs 8/kWh at ~6.5 km/kWh

COLUMNS = ["Brand", "Model", "Body_Type", "Segment", "Year", "Fuel_Type", "Transmission", "Price", "Mileage", "Range_km",
           "Engine_CC", "Power_bhp", "Seating_Capacity", "Service_Cost", "Cost_Per_Km", "Ultra_Luxury", "Offroad"]

# ---- words the language parser knows (shared by the Python server and the in-browser engine)
BRAND_WORDS = {
    "honda": "Honda", "hyundai": "Hyundai", "kia": "Kia", "mahindra": "Mahindra", "maruti": "Maruti Suzuki",
    "suzuki": "Maruti Suzuki", "renault": "Renault", "nissan": "Nissan", "skoda": "Skoda", "tata": "Tata Motors",
    "toyota": "Toyota", "volkswagen": "Volkswagen", "vw": "Volkswagen", "mg": "MG", "jeep": "Jeep", "citroen": "Citroen",
    "byd": "BYD", "mercedes": "Mercedes-Benz", "mercedesbenz": "Mercedes-Benz", "benz": "Mercedes-Benz", "merc": "Mercedes-Benz",
    "bmw": "BMW", "audi": "Audi", "volvo": "Volvo", "jaguar": "Jaguar", "landrover": "Land Rover", "lexus": "Lexus",
    "porsche": "Porsche", "rollsroyce": "Rolls-Royce", "bentley": "Bentley", "lamborghini": "Lamborghini",
    "lambo": "Lamborghini", "ferrari": "Ferrari", "maserati": "Maserati", "astonmartin": "Aston Martin",
}
# "german luxury", "korean suv": a country stands for several brands
ORIGINS = {
    "german": ["Mercedes-Benz", "BMW", "Audi", "Porsche", "Volkswagen"], "japanese": ["Toyota", "Honda", "Nissan", "Lexus", "Maruti Suzuki"],
    "korean": ["Hyundai", "Kia"], "indian": ["Tata Motors", "Mahindra"], "american": ["Jeep"], "chinese": ["MG", "BYD"],
    "italian": ["Ferrari", "Lamborghini", "Maserati"], "british": ["Jaguar", "Land Rover", "Bentley", "Rolls-Royce", "Aston Martin", "MINI"],
    "swedish": ["Volvo"], "french": ["Renault", "Citroen"], "czech": ["Skoda"],
}
# model words that are also everyday words: only read as a car when a brand comes right before them
AMBIGUOUS = ["city", "punch", "seal", "compass", "safari", "ghost", "roma", "cooper", "vantage", "defender", "golf", "windsor",
             "comet", "be6"]
# what people actually type -> the model name in the catalogue
ALIASES = {
    "innova": "Innova Crysta", "crysta": "Innova Crysta", "hycross": "Innova Hycross", "zenix": "Innova Hycross",
    "alto": "Alto K10", "wagonr": "Wagon R", "i10": "Grand i10 Nios", "grand i10": "Grand i10 Nios", "nios": "Grand i10 Nios",
    "scorpio": "Scorpio-N", "hyryder": "Urban Cruiser Hyryder", "taisor": "Urban Cruiser Taisor", "3xo": "XUV 3XO",
    "land cruiser": "Land Cruiser 300", "landcruiser": "Land Cruiser 300", "etron": "Q8 e-tron", "evoque": "Range Rover Evoque",
    "velar": "Range Rover Velar", "3 series": "3 Series Gran Limousine", "2 series": "2 Series Gran Coupe", "ioniq": "Ioniq 5",
    "amg gt": "AMG GT 63", "m4": "M4 Competition", "cayman": "718 Cayman", "gti": "Golf GTI", "golf": "Golf GTI",
    "creta ev": "Creta Electric", "mahindra be 6": "BE 6", "mahindra be6": "BE 6", "mg windsor": "Windsor EV", "windsor": "Windsor EV",
    "comet": "Comet EV", "mini cooper": "Cooper", "mini cooper se": "Cooper SE", "mini countryman": "Countryman Electric", "countryman": "Countryman Electric", "dbx": "DBX707",
}
# Body-on-frame / 4x4-capable models that people mean by "off-roader" (hand-picked; crossovers like Creta or Seltos are not on this list)
OFFROAD_MODELS = {"Jimny", "Thar", "Thar Roxx", "Bolero", "Bolero Neo", "Scorpio Classic", "Scorpio-N", "Fortuner", "Gloster", "Land Cruiser 300",
                  "Wrangler", "Defender", "Discovery Sport", "G-Class", "LX 500d", "Range Rover", "Range Rover Sport"}
ULTRA_LAKH = 250              # models typically priced above Rs 2.5 crore: the "billionaire" tier (Rolls-Royce, Bentley, Ferrari, Lamborghini ...)
LUXURY_PRICE_LAKH = 60        # a model whose typical price is above this is treated as luxury even from a mass brand
MAX_RELIABLE_YEAR = 2025


def jitter(key, spread):
    """Deterministic +/- spread (so the CSV is reproducible without a random seed)."""
    return (zlib.crc32(key.encode()) % 1001 / 1000 * 2 - 1) * spread


def service_cost(brand, fuel, price):
    luxury = brand in LUXURY_BRANDS
    base = price * 0.0055 if luxury else 3500 + price * 0.0042
    base *= 0.6 if fuel == "Electric" else 1.0
    return int(round(base * (1 + jitter(f"{brand}{fuel}{price}", 0.06)), -2))


def segment_of(brand, median_price):
    if brand in LUXURY_BRANDS or median_price >= LUXURY_PRICE_LAKH * 1e5:
        return "Luxury"
    if median_price >= 20e5:
        return "Premium"
    return "Budget" if median_price < 8e5 else "Mainstream"


def rows():
    out = []
    for brand, models in CATALOG.items():
        for model, body, seats, year, variants in models:
            model_rows = []
            for fuel, gears, cc, eff, bhp, lo, hi in variants:
                combos = {"M": ["Manual"], "A": ["Automatic"], "MA": ["Manual", "Automatic"]}[gears]
                for trans in combos:
                    # manuals sit in the lower part of the price band, automatics in the upper part
                    a, b = (lo, hi) if len(combos) == 1 else ((lo, lo + 0.6 * (hi - lo)) if trans == "Manual" else (lo + 0.4 * (hi - lo), hi))
                    for t in (0.0, 0.5, 1.0):
                        price = int(round((a + (b - a) * t) * 1e5, -4))
                        ev = fuel == "Electric"
                        model_rows.append(dict(
                            Brand=brand, Model=model, Body_Type=body, Year=year, Fuel_Type=fuel, Transmission=trans, Price=price,
                            Mileage="" if ev else eff, Range_km=int(eff) if ev else "", Engine_CC=cc if cc else "", Power_bhp=bhp,
                            Seating_Capacity=seats, Service_Cost=service_cost(brand, fuel, price),
                            Cost_Per_Km=round(EV_COST_PER_KM if ev else FUEL_PRICE[fuel] / eff, 2)))
            prices = sorted(r["Price"] for r in model_rows)
            seg = segment_of(brand, prices[len(prices) // 2])
            for r in model_rows:
                r["Segment"] = seg
                r["Ultra_Luxury"] = int(prices[len(prices) // 2] >= ULTRA_LAKH * 1e5)
                r["Offroad"] = int(model in OFFROAD_MODELS)
            out.extend(model_rows)
    return out


def main():
    data = rows()
    (BASE / "data").mkdir(exist_ok=True)
    with open(BASE / "data" / "cars_india.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(data)

    names = [m[0] for ms in CATALOG.values() for m in ms]
    assert len(names) == len(set(names)), "model names must be unique across brands"
    brands = sorted(CATALOG)
    models = sorted({r["Model"] for r in data})
    fuels = sorted({r["Fuel_Type"] for r in data})
    trans = ["Automatic", "Manual"]
    body = {r["Model"]: r["Body_Type"] for r in data}
    segment = {r["Model"]: r["Segment"] for r in data}
    assert OFFROAD_MODELS <= set(models), OFFROAD_MODELS - set(models)
    ultra = sorted({r["Model"] for r in data if r["Ultra_Luxury"]})
    offroad = sorted(OFFROAD_MODELS)
    model_brand = {r["Model"]: r["Brand"] for r in data}
    lex = {"brands": BRAND_WORDS, "ambiguous": AMBIGUOUS, "aliases": ALIASES, "origins": ORIGINS}
    for k, v in ALIASES.items():
        assert v in models, f"alias {k!r} points at unknown model {v!r}"
    for v in [x for bs in ORIGINS.values() for x in bs] + list(BRAND_WORDS.values()):
        assert v in CATALOG, f"brand word points at unknown brand {v!r}"

    packed = [[brands.index(r["Brand"]), models.index(r["Model"]), r["Year"], r["Price"],
               None if r["Mileage"] == "" else r["Mileage"], None if r["Range_km"] == "" else r["Range_km"],
               None if r["Engine_CC"] == "" else r["Engine_CC"], r["Power_bhp"], r["Seating_Capacity"], r["Service_Cost"],
               r["Cost_Per_Km"], fuels.index(r["Fuel_Type"]), trans.index(r["Transmission"])] for r in data]
    img_dir = BASE / "car_images"
    images = {p.stem.lower(): p.name for p in img_dir.glob("*.*") if p.suffix.lower() != ".txt"} if img_dir.exists() else {}
    js = {"brands": brands, "models": models, "fuels": fuels, "trans": trans, "body": body, "segment": segment, "ultra": ultra, "offroad": offroad,
          "modelBrand": model_brand, "lex": lex, "rows": packed, "images": images}
    (BASE / "data" / "lexicon.json").write_text(json.dumps(lex, indent=1), encoding="utf-8")
    (BASE / "frontend" / "cars-data.js").write_text("window.CARS_DATA=" + json.dumps(js, separators=(",", ":")) + ";", encoding="utf-8")
    print(f"{len(data)} listings, {len(models)} models, {len(brands)} brands -> data/cars_india.csv, data/lexicon.json, frontend/cars-data.js")


if __name__ == "__main__":
    main()
