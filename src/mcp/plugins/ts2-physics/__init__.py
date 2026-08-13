import json
import logging
import math
from typing import Any, Dict

logger = logging.getLogger(__name__)

PHYSICS_CONSTANTS_SCHEMA = {
    "name": "physics_constants",
    "description": "查询物理常数。支持力学、电磁学、热力学、量子力学、光学等领域的常用常数。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要查询的常数名称或关键词，如 '光速'、'planck'、'electron mass'",
            },
            "category": {
                "type": "string",
                "enum": ["all", "mechanics", "electromagnetism", "thermodynamics", "quantum", "optics", "nuclear"],
                "description": "按分类筛选常数，默认 all",
            },
        },
        "required": [],
    },
}

UNIT_CONVERT_SCHEMA = {
    "name": "unit_convert",
    "description": "物理单位转换。支持长度、质量、时间、温度、能量、力、压力、电磁等常见物理单位互转。",
    "parameters": {
        "type": "object",
        "properties": {
            "value": {
                "type": "number",
                "description": "待转换的数值",
            },
            "from_unit": {
                "type": "string",
                "description": "源单位，如 'eV', 'nm', 'kg', 'K'",
            },
            "to_unit": {
                "type": "string",
                "description": "目标单位，如 'J', 'm', 'g', '°C'",
            },
        },
        "required": ["value", "from_unit", "to_unit"],
    },
}

FORMULA_COMPUTE_SCHEMA = {
    "name": "formula_compute",
    "description": "物理公式计算。输入公式名称和已知量，自动计算未知量。支持力学、电磁学、热力学、量子力学等常见公式。",
    "parameters": {
        "type": "object",
        "properties": {
            "formula": {
                "type": "string",
                "description": "公式名称，如 'kinetic_energy', 'coulomb_force', 'planck_energy', 'ideal_gas'",
            },
            "variables": {
                "type": "object",
                "description": "已知变量及其数值，如 {'mass': 2.0, 'velocity': 3.0}",
            },
            "solve_for": {
                "type": "string",
                "description": "要求解的未知量名称，如 'energy'",
            },
        },
        "required": ["formula", "variables"],
    },
}

_PHYSICS_CONSTANTS = [
    {"name": "光速", "symbol": "c", "value": 299792458, "unit": "m/s", "category": "mechanics", "aliases": ["speed of light", "c"]},
    {"name": "万有引力常数", "symbol": "G", "value": 6.67430e-11, "unit": "m³/(kg·s²)", "category": "mechanics", "aliases": ["gravitational constant", "G"]},
    {"name": "普朗克常数", "symbol": "h", "value": 6.62607015e-34, "unit": "J·s", "category": "quantum", "aliases": ["planck constant", "h"]},
    {"name": "约化普朗克常数", "symbol": "ℏ", "value": 1.054571817e-34, "unit": "J·s", "category": "quantum", "aliases": ["reduced planck", "hbar"]},
    {"name": "基本电荷", "symbol": "e", "value": 1.602176634e-19, "unit": "C", "category": "electromagnetism", "aliases": ["elementary charge", "e"]},
    {"name": "电子质量", "symbol": "mₑ", "value": 9.1093837015e-31, "unit": "kg", "category": "quantum", "aliases": ["electron mass", "me"]},
    {"name": "质子质量", "symbol": "mₚ", "value": 1.67262192369e-27, "unit": "kg", "category": "nuclear", "aliases": ["proton mass", "mp"]},
    {"name": "中子质量", "symbol": "mₙ", "value": 1.67492749804e-27, "unit": "kg", "category": "nuclear", "aliases": ["neutron mass", "mn"]},
    {"name": "真空介电常数", "symbol": "ε₀", "value": 8.8541878128e-12, "unit": "F/m", "category": "electromagnetism", "aliases": ["permittivity", "epsilon_0", "ε0"]},
    {"name": "真空磁导率", "symbol": "μ₀", "value": 1.25663706212e-6, "unit": "H/m", "category": "electromagnetism", "aliases": ["permeability", "mu_0", "μ0"]},
    {"name": "玻尔兹曼常数", "symbol": "k_B", "value": 1.380649e-23, "unit": "J/K", "category": "thermodynamics", "aliases": ["boltzmann constant", "kb", "k_B"]},
    {"name": "阿伏伽德罗常数", "symbol": "N_A", "value": 6.02214076e23, "unit": "mol⁻¹", "category": "thermodynamics", "aliases": ["avogadro", "NA", "N_A"]},
    {"name": "气体常数", "symbol": "R", "value": 8.314462618, "unit": "J/(mol·K)", "category": "thermodynamics", "aliases": ["gas constant", "R"]},
    {"name": "法拉第常数", "symbol": "F", "value": 96485.33212, "unit": "C/mol", "category": "electromagnetism", "aliases": ["faraday constant", "F"]},
    {"name": "斯特藩-玻尔兹曼常数", "symbol": "σ", "value": 5.670374419e-8, "unit": "W/(m²·K⁴)", "category": "thermodynamics", "aliases": ["stefan-boltzmann", "sigma"]},
    {"name": "维恩位移常数", "symbol": "b", "value": 2.897771955e-3, "unit": "m·K", "category": "thermodynamics", "aliases": ["wien", "b"]},
    {"name": "里德伯常数", "symbol": "R∞", "value": 10973731.568160, "unit": "m⁻¹", "category": "quantum", "aliases": ["rydberg", "R_inf"]},
    {"name": "玻尔半径", "symbol": "a₀", "value": 5.29177210903e-11, "unit": "m", "category": "quantum", "aliases": ["bohr radius", "a0"]},
    {"name": "精细结构常数", "symbol": "α", "value": 7.2973525693e-3, "unit": "", "category": "quantum", "aliases": ["fine structure", "alpha"]},
    {"name": "电子伏特", "symbol": "eV", "value": 1.602176634e-19, "unit": "J", "category": "electromagnetism", "aliases": ["electronvolt"]},
    {"name": "原子质量单位", "symbol": "u", "value": 1.66053906660e-27, "unit": "kg", "category": "nuclear", "aliases": ["amu", "u", "dalton"]},
    {"name": "标准重力加速度", "symbol": "g", "value": 9.80665, "unit": "m/s²", "category": "mechanics", "aliases": ["gravity", "g"]},
    {"name": "库仑常数", "symbol": "k_e", "value": 8.9875517923e9, "unit": "N·m²/C²", "category": "electromagnetism", "aliases": ["coulomb constant", "ke"]},
]

_UNIT_CONVERSIONS = {
    "length": {
        "m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "um": 1e-6, "nm": 1e-9,
        "pm": 1e-12, "fm": 1e-15, "AU": 1.496e11, "ly": 9.461e15, "pc": 3.086e16,
        "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344,
    },
    "mass": {
        "kg": 1.0, "g": 0.001, "mg": 1e-6, "ug": 1e-9, "u": 1.66053906660e-27,
        "lb": 0.45359237, "oz": 0.028349523125, "ton": 1000.0,
    },
    "time": {
        "s": 1.0, "ms": 0.001, "us": 1e-6, "ns": 1e-9, "ps": 1e-12,
        "min": 60.0, "h": 3600.0, "d": 86400.0, "yr": 3.156e7,
    },
    "energy": {
        "J": 1.0, "kJ": 1000.0, "MJ": 1e6, "eV": 1.602176634e-19,
        "keV": 1.602176634e-16, "MeV": 1.602176634e-13, "GeV": 1.602176634e-10,
        "cal": 4.184, "kcal": 4184.0, "erg": 1e-7, "eV": 1.602176634e-19,
        "BTU": 1055.06, "Wh": 3600.0, "kWh": 3.6e6,
    },
    "force": {
        "N": 1.0, "kN": 1000.0, "MN": 1e6, "dyn": 1e-5, "lbf": 4.4482216152605,
        "kgf": 9.80665,
    },
    "pressure": {
        "Pa": 1.0, "kPa": 1000.0, "MPa": 1e6, "GPa": 1e9,
        "bar": 1e5, "atm": 101325.0, "mmHg": 133.322, "Torr": 133.322,
        "psi": 6894.757,
    },
    "temperature_special": True,
    "angle": {
        "rad": 1.0, "deg": math.pi / 180.0, "arcmin": math.pi / 10800.0,
        "arcsec": math.pi / 648000.0,
    },
    "electromagnetic": {
        "C": 1.0, "mC": 0.001, "uC": 1e-6, "nC": 1e-9,
        "V": 1.0, "mV": 0.001, "kV": 1000.0, "MV": 1e6,
        "A": 1.0, "mA": 0.001, "uA": 1e-6, "nA": 1e-9,
        "ohm": 1.0, "kohm": 1000.0, "Mohm": 1e6,
        "T": 1.0, "mT": 0.001, "uT": 1e-6, "G": 1e-4, "mG": 1e-7,
        "F": 1.0, "mF": 0.001, "uF": 1e-6, "nF": 1e-9, "pF": 1e-12,
        "H": 1.0, "mH": 0.001, "uH": 1e-6,
        "Wb": 1.0, "mWb": 0.001,
    },
}

_FORMULAS = {
    "kinetic_energy": {
        "description": "动能: E_k = ½mv²",
        "variables": ["mass", "velocity", "energy"],
        "compute": lambda v: 0.5 * v["mass"] * v["velocity"] ** 2 if "energy" not in v else None,
        "solve": {
            "energy": lambda v: 0.5 * v["mass"] * v["velocity"] ** 2,
            "mass": lambda v: 2 * v["energy"] / v["velocity"] ** 2,
            "velocity": lambda v: math.sqrt(2 * v["energy"] / v["mass"]),
        },
    },
    "potential_energy": {
        "description": "重力势能: E_p = mgh",
        "variables": ["mass", "height", "energy", "g"],
        "compute": lambda v: v.get("mass", 0) * v.get("g", 9.80665) * v.get("height", 0),
        "solve": {
            "energy": lambda v: v["mass"] * v.get("g", 9.80665) * v["height"],
            "mass": lambda v: v["energy"] / (v.get("g", 9.80665) * v["height"]),
            "height": lambda v: v["energy"] / (v["mass"] * v.get("g", 9.80665)),
        },
    },
    "coulomb_force": {
        "description": "库仑力: F = k_e·q₁·q₂/r²",
        "variables": ["q1", "q2", "distance", "force"],
        "solve": {
            "force": lambda v: 8.9875517923e9 * v["q1"] * v["q2"] / v["distance"] ** 2,
            "q1": lambda v: v["force"] * v["distance"] ** 2 / (8.9875517923e9 * v["q2"]),
            "distance": lambda v: math.sqrt(8.9875517923e9 * v["q1"] * v["q2"] / v["force"]),
        },
    },
    "gravitational_force": {
        "description": "万有引力: F = G·m₁·m₂/r²",
        "variables": ["m1", "m2", "distance", "force"],
        "solve": {
            "force": lambda v: 6.67430e-11 * v["m1"] * v["m2"] / v["distance"] ** 2,
            "m1": lambda v: v["force"] * v["distance"] ** 2 / (6.67430e-11 * v["m2"]),
            "distance": lambda v: math.sqrt(6.67430e-11 * v["m1"] * v["m2"] / v["force"]),
        },
    },
    "planck_energy": {
        "description": "光子能量: E = hf = hc/λ",
        "variables": ["frequency", "wavelength", "energy"],
        "solve": {
            "energy": lambda v: 6.62607015e-34 * v.get("frequency", 299792458 / v["wavelength"] if "wavelength" in v else 0),
            "frequency": lambda v: v["energy"] / 6.62607015e-34,
            "wavelength": lambda v: 6.62607015e-34 * 299792458 / v["energy"],
        },
        "optional_vars": ["frequency", "wavelength"],
    },
    "de_broglie": {
        "description": "德布罗意波长: λ = h/p = h/(mv)",
        "variables": ["mass", "velocity", "wavelength", "momentum"],
        "solve": {
            "wavelength": lambda v: 6.62607015e-34 / (v.get("momentum", v["mass"] * v["velocity"])),
            "momentum": lambda v: 6.62607015e-34 / v["wavelength"],
            "velocity": lambda v: 6.62607015e-34 / (v["mass"] * v["wavelength"]),
        },
    },
    "ideal_gas": {
        "description": "理想气体状态方程: PV = nRT",
        "variables": ["pressure", "volume", "moles", "temperature"],
        "solve": {
            "pressure": lambda v: v["moles"] * 8.314462618 * v["temperature"] / v["volume"],
            "volume": lambda v: v["moles"] * 8.314462618 * v["temperature"] / v["pressure"],
            "moles": lambda v: v["pressure"] * v["volume"] / (8.314462618 * v["temperature"]),
            "temperature": lambda v: v["pressure"] * v["volume"] / (v["moles"] * 8.314462618),
        },
    },
    "lorentz_force": {
        "description": "洛伦兹力: F = qvB (垂直磁场)",
        "variables": ["charge", "velocity", "magnetic_field", "force"],
        "solve": {
            "force": lambda v: v["charge"] * v["velocity"] * v["magnetic_field"],
            "charge": lambda v: v["force"] / (v["velocity"] * v["magnetic_field"]),
            "velocity": lambda v: v["force"] / (v["charge"] * v["magnetic_field"]),
            "magnetic_field": lambda v: v["force"] / (v["charge"] * v["velocity"]),
        },
    },
    "schwarzschild_radius": {
        "description": "史瓦西半径: r_s = 2GM/c²",
        "variables": ["mass", "radius"],
        "solve": {
            "radius": lambda v: 2 * 6.67430e-11 * v["mass"] / 299792458 ** 2,
            "mass": lambda v: v["radius"] * 299792458 ** 2 / (2 * 6.67430e-11),
        },
    },
    "wave_equation": {
        "description": "波方程: v = fλ",
        "variables": ["velocity", "frequency", "wavelength"],
        "solve": {
            "velocity": lambda v: v["frequency"] * v["wavelength"],
            "frequency": lambda v: v["velocity"] / v["wavelength"],
            "wavelength": lambda v: v["velocity"] / v["frequency"],
        },
    },
}


def _find_unit_category(unit: str) -> str:
    for cat, data in _UNIT_CONVERSIONS.items():
        if isinstance(data, dict) and unit in data:
            return cat
    return ""


def _handle_physics_constants(args: dict, **kw) -> str:
    query = (args.get("query") or "").strip().lower()
    category = args.get("category", "all")

    results = []
    for const in _PHYSICS_CONSTANTS:
        if category != "all" and const["category"] != category:
            continue
        if query:
            match = (
                query in const["name"].lower()
                or query in const["symbol"].lower()
                or any(query in alias.lower() for alias in const["aliases"])
                or query in const["category"].lower()
            )
            if not match:
                continue
        results.append({
            "name": const["name"],
            "symbol": const["symbol"],
            "value": const["value"],
            "unit": const["unit"],
            "category": const["category"],
        })

    if not results and query:
        return json.dumps({"success": True, "results": [], "message": f"未找到匹配 '{query}' 的常数"})

    return json.dumps({"success": True, "results": results, "count": len(results)})


def _handle_unit_convert(args: dict, **kw) -> str:
    value = args.get("value")
    from_unit = (args.get("from_unit") or "").strip()
    to_unit = (args.get("to_unit") or "").strip()

    if value is None or not from_unit or not to_unit:
        return json.dumps({"success": False, "error": "需要 value, from_unit, to_unit 三个参数"})

    try:
        value = float(value)
    except (TypeError, ValueError):
        return json.dumps({"success": False, "error": f"无效数值: {value}"})

    temp_from = from_unit.lower() in ("c", "°c", "degc", "celsius")
    temp_to = to_unit.lower() in ("c", "°c", "degc", "celsius")
    temp_from_f = from_unit.lower() in ("f", "°f", "degf", "fahrenheit")
    temp_to_f = to_unit.lower() in ("f", "°f", "degf", "fahrenheit")
    temp_from_k = from_unit.lower() in ("k", "kelvin")
    temp_to_k = to_unit.lower() in ("k", "kelvin")

    if temp_from or temp_to or temp_from_f or temp_to_f or temp_from_k or temp_to_k:
        return _convert_temperature(value, from_unit, to_unit)

    from_cat = _find_unit_category(from_unit)
    to_cat = _find_unit_category(to_unit)

    if not from_cat:
        return json.dumps({"success": False, "error": f"未知单位: {from_unit}"})
    if not to_cat:
        return json.dumps({"success": False, "error": f"未知单位: {to_unit}"})
    if from_cat != to_cat:
        return json.dumps({"success": False, "error": f"单位类别不匹配: {from_unit}({from_cat}) vs {to_unit}({to_cat})"})

    from_data = _UNIT_CONVERSIONS[from_cat]
    to_data = _UNIT_CONVERSIONS[to_cat]

    si_value = value * from_data[from_unit]
    result = si_value / to_data[to_unit]

    return json.dumps({
        "success": True,
        "value": value,
        "from_unit": from_unit,
        "to_unit": to_unit,
        "result": result,
        "category": from_cat,
    })


def _convert_temperature(value: float, from_unit: str, to_unit: str) -> str:
    fu = from_unit.lower()
    tu = to_unit.lower()

    if fu in ("k", "kelvin"):
        kelvin = value
    elif fu in ("c", "°c", "degc", "celsius"):
        kelvin = value + 273.15
    elif fu in ("f", "°f", "degf", "fahrenheit"):
        kelvin = (value - 32) * 5 / 9 + 273.15
    else:
        return json.dumps({"success": False, "error": f"未知温度单位: {from_unit}"})

    if tu in ("k", "kelvin"):
        result = kelvin
    elif tu in ("c", "°c", "degc", "celsius"):
        result = kelvin - 273.15
    elif tu in ("f", "°f", "degf", "fahrenheit"):
        result = (kelvin - 273.15) * 9 / 5 + 32
    else:
        return json.dumps({"success": False, "error": f"未知温度单位: {to_unit}"})

    return json.dumps({
        "success": True,
        "value": value,
        "from_unit": from_unit,
        "to_unit": to_unit,
        "result": result,
        "category": "temperature",
    })


def _handle_formula_compute(args: dict, **kw) -> str:
    formula_name = (args.get("formula") or "").strip().lower()
    variables = args.get("variables", {})
    solve_for = (args.get("solve_for") or "").strip()

    if not formula_name:
        return json.dumps({"success": False, "error": "需要 formula 参数"})

    formula = _FORMULAS.get(formula_name)
    if not formula:
        available = ", ".join(sorted(_FORMULAS.keys()))
        return json.dumps({"success": False, "error": f"未知公式: {formula_name}。可用公式: {available}"})

    try:
        num_vars = {k: float(v) for k, v in variables.items()}
    except (TypeError, ValueError) as exc:
        return json.dumps({"success": False, "error": f"变量值无效: {exc}"})

    if solve_for:
        solver = formula["solve"].get(solve_for)
        if not solver:
            available = ", ".join(formula["solve"].keys())
            return json.dumps({"success": False, "error": f"无法求解 {solve_for}。可求解: {available}"})

        optional = set(formula.get("optional_vars", []))
        required_vars = [v for v in formula["variables"] if v != solve_for and v not in optional]
        missing = [v for v in required_vars if v not in num_vars]
        if missing:
            return json.dumps({"success": False, "error": f"缺少变量: {missing}"})

        result = solver(num_vars)
        return json.dumps({
            "success": True,
            "formula": formula_name,
            "description": formula["description"],
            "solve_for": solve_for,
            "result": result,
            "given": num_vars,
        })
    else:
        given = set(num_vars.keys())
        needed = set(formula["variables"])
        missing = needed - given

        if not missing:
            compute_fn = formula.get("compute")
            if compute_fn:
                result = compute_fn(num_vars)
                return json.dumps({
                    "success": True,
                    "formula": formula_name,
                    "description": formula["description"],
                    "result": result,
                    "given": num_vars,
                })

        solvable = []
        for var in missing:
            if var in formula["solve"]:
                required_for = [v for v in formula["variables"] if v != var]
                if all(v in given for v in required_for):
                    solvable.append(var)

        if len(solvable) == 1:
            solver = formula["solve"][solvable[0]]
            result = solver(num_vars)
            return json.dumps({
                "success": True,
                "formula": formula_name,
                "description": formula["description"],
                "auto_solved": solvable[0],
                "result": result,
                "given": num_vars,
            })
        elif len(solvable) > 1:
            return json.dumps({
                "success": False,
                "error": f"多个未知量可求解: {solvable}，请指定 solve_for",
                "formula": formula_name,
                "given": num_vars,
            })
        else:
            return json.dumps({
                "success": False,
                "error": f"缺少变量且无法自动求解: {missing}",
                "formula": formula_name,
                "given": num_vars,
            })


def register(ctx) -> None:
    ctx.register_tool(
        name="physics_constants",
        toolset="ts2-physics",
        schema=PHYSICS_CONSTANTS_SCHEMA,
        handler=_handle_physics_constants,
        emoji="⚛️",
    )
    ctx.register_tool(
        name="unit_convert",
        toolset="ts2-physics",
        schema=UNIT_CONVERT_SCHEMA,
        handler=_handle_unit_convert,
        emoji="🔄",
    )
    ctx.register_tool(
        name="formula_compute",
        toolset="ts2-physics",
        schema=FORMULA_COMPUTE_SCHEMA,
        handler=_handle_formula_compute,
        emoji="📐",
    )
    logger.info("ts2-physics plugin registered")
