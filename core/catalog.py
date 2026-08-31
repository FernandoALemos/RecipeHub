MEASUREMENT_TYPES = [
    ("mass", "Mass"),
    ("volume", "Volume"),
    ("count", "Count"),
    ("culinary_volume", "Culinary volume"),
    ("informal", "Informal"),
]

UNITS = [
    ("g", "g — gramos"),
    ("kg", "kg — kilogramos"),
    ("ml", "ml — mililitros"),
    ("l", "l — litros"),
    ("unit", "unit — unidad"),
    ("half_unit", "half_unit — media unidad"),
    ("clove", "clove — diente"),
    ("dozen", "dozen — docena"),
    ("half_dozen", "half_dozen — media docena"),
    ("yolk", "yolk — yema"),
    ("white", "white — clara"),
    ("tsp", "tsp — cucharadita"),
    ("tbsp", "tbsp — cucharada"),
    ("cup", "cup — taza"),
    ("pinch", "pinch — pizca"),
    ("handful", "handful — puñado"),
    ("to_taste", "to_taste — a gusto"),
]

UNIT_CODES = [code for code, _label in UNITS]
MEASUREMENT_TYPE_CODES = [code for code, _label in MEASUREMENT_TYPES]
