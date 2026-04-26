#!/usr/bin/env python3
"""
Torque Engine - výpočetní jádro generátoru momentových křivek.

Obsahuje matematiku náběhových křivek, generování sekvencí, analýzu
a ukládání do CSV. Nemá žádné závislosti na UI – lze testovat izolovaně.
"""

import csv
import math
import os
from typing import List, Tuple

# Platné identifikátory typů náběhu
RAMP_TYPES = ("hybrid", "exponential", "scurve", "linear")


# ---------------------------------------------------------------------------
# Náběhové funkce
# ---------------------------------------------------------------------------

def hybrid_ramp(angle: float, max_angle: float, target_torque: float) -> float:
    """Hybridní náběh: exponenciální (0–40 %) → lineární (40–80 %) → S-křivka (80–100 %).

    Doporučeno pro PID regulaci – rychlý start s hladkým dosednutím.

    Args:
        angle: Aktuální úhel [°]
        max_angle: Celkový úhel náběhové fáze [°]
        target_torque: Cílový moment [Nm]

    Returns:
        Momentová hodnota v daném úhlu [Nm]
    """
    progress = angle / max_angle

    if progress <= 0.4:
        p = progress / 0.4
        return target_torque * 0.7 * (math.exp(2.5 * p) - 1) / (math.exp(2.5) - 1)
    elif progress <= 0.8:
        p = (progress - 0.4) / 0.4
        return target_torque * (0.7 + 0.25 * p)
    else:
        p = (progress - 0.8) / 0.2
        s = (math.tanh(6 * (p - 0.5)) + 1) / 2
        return target_torque * (0.95 + 0.05 * s)


def exponential_ramp(angle: float, max_angle: float, target_torque: float) -> float:
    """Exponenciální náběh se sigmoid doladěním posledních 40 %.

    Rychlý start – vhodné tam, kde záleží na době dosažení pracovního momentu.

    Args:
        angle: Aktuální úhel [°]
        max_angle: Celkový úhel náběhové fáze [°]
        target_torque: Cílový moment [Nm]

    Returns:
        Momentová hodnota v daném úhlu [Nm]
    """
    progress = angle / max_angle

    if progress <= 0.6:
        p = progress / 0.6
        return target_torque * 0.9 * (math.exp(3.5 * p) - 1) / (math.exp(3.5) - 1)
    else:
        p = (progress - 0.6) / 0.4
        sigmoid = 1 / (1 + math.exp(-12 * (p - 0.5)))
        return target_torque * (0.9 + 0.1 * sigmoid)


def scurve_ramp(angle: float, max_angle: float, target_torque: float) -> float:
    """S-křivka (hyperbolický tangens) – nejhladší náběh bez overshootu.

    Vhodné pro aplikace citlivé na rázy a přesnou polohu.

    Args:
        angle: Aktuální úhel [°]
        max_angle: Celkový úhel náběhové fáze [°]
        target_torque: Cílový moment [Nm]

    Returns:
        Momentová hodnota v daném úhlu [Nm]
    """
    progress = angle / max_angle
    return target_torque * (math.tanh(4 * (progress - 0.5)) + 1) / 2


def linear_ramp(angle: float, max_angle: float, target_torque: float) -> float:
    """Lineární náběh – klasický přístup s konstantní rychlostí nárůstu.

    Args:
        angle: Aktuální úhel [°]
        max_angle: Celkový úhel náběhové fáze [°]
        target_torque: Cílový moment [Nm]

    Returns:
        Momentová hodnota v daném úhlu [Nm]
    """
    return target_torque * (angle / max_angle)


# Interní mapa pro dispatch dle řetězcového klíče
_RAMP_FUNCTIONS = {
    "hybrid": hybrid_ramp,
    "exponential": exponential_ramp,
    "scurve": scurve_ramp,
    "linear": linear_ramp,
}


# ---------------------------------------------------------------------------
# Generování křivky
# ---------------------------------------------------------------------------

def generate_curve(
    target_torque: float,
    working_degrees: float,
    ramp_type: str = "hybrid",
    ramp_degrees: float = 45.0,
    end_with_block: bool = False,
    block_torque: float = 50.0,
) -> List[Tuple[float, float]]:
    """Generuje momentovou křivku jako list (torque, angle) dvojic po 1°.

    Sekvence: náběhová fáze → pracovní fáze → volitelný blok (3 body).
    Vždy vrací kladné hodnoty – směrové znaménko aplikuje apply_direction_mapping.

    Args:
        target_torque: Cílový pracovní moment [Nm] (musí být > 0)
        working_degrees: Délka pracovní fáze [°] (musí být > 0)
        ramp_type: Typ náběhu – "hybrid", "exponential", "scurve", "linear"
        ramp_degrees: Délka náběhové fáze [°] (>= 0)
        end_with_block: Přidat blokový moment na konec (3 body navíc)
        block_torque: Hodnota blokového momentu [Nm]

    Returns:
        List dvojic (torque [Nm], angle [°]) s kladnými hodnotami

    Raises:
        ValueError: Pro neplatné vstupní parametry
    """
    if target_torque <= 0:
        raise ValueError(f"Cílový moment musí být kladný, zadáno: {target_torque}")
    if working_degrees <= 0:
        raise ValueError(f"Pracovní rozsah musí být kladný, zadáno: {working_degrees}")
    if ramp_degrees < 0:
        raise ValueError(f"Úhel náběhu nesmí být záporný, zadáno: {ramp_degrees}")
    if ramp_type not in _RAMP_FUNCTIONS:
        raise ValueError(f"Neznámý typ náběhu: '{ramp_type}'. Platné: {RAMP_TYPES}")

    ramp_fn = _RAMP_FUNCTIONS[ramp_type]
    total_degrees = ramp_degrees + working_degrees
    data: List[Tuple[float, float]] = []

    for angle in range(int(total_degrees) + 1):
        if ramp_degrees > 0 and angle <= ramp_degrees:
            torque = ramp_fn(angle, ramp_degrees, target_torque)
        else:
            torque = target_torque
        data.append((round(torque, 2), float(angle)))

    if end_with_block:
        final_angle = data[-1][1]
        for i in range(1, 4):
            data.append((round(block_torque, 2), final_angle + i))

    return data


# ---------------------------------------------------------------------------
# Směrové mapování
# ---------------------------------------------------------------------------

def apply_direction_mapping(
    data: List[Tuple[float, float]],
    motor_type: str,
    direction: str,
) -> List[Tuple[float, float]]:
    """Aplikuje směrové znaménko na moment i úhel podle konvence motoru.

    Konvence znamének:
        LH + CCW → kladné hodnoty  (+)
        LH + CW  → záporné hodnoty (-)
        RH + CCW → záporné hodnoty (-)
        RH + CW  → kladné hodnoty  (+)

    Args:
        data: Vstupní data (torque, angle) – předpokládají se kladné hodnoty
        motor_type: Typ motoru – "LH" nebo "RH"
        direction: Směr otáčení – "CCW" nebo "CW"

    Returns:
        Data s aplikovaným znaménkem (torque, angle)
    """
    # XOR: LH+CCW nebo RH+CW → kladné; ostatní kombinace → záporné
    sign = 1 if (motor_type == "LH") == (direction == "CCW") else -1
    return [(round(t * sign, 2), round(a * sign, 2)) for t, a in data]


# ---------------------------------------------------------------------------
# Analýza křivky
# ---------------------------------------------------------------------------

def analyze_curve(
    data: List[Tuple[float, float]],
    target_torque: float,
) -> dict:
    """Analyzuje rychlost dosažení cílového momentu v křivce.

    Pracuje s absolutními hodnotami, takže je kompatibilní s mapovanými
    i nemapovanými daty.

    Args:
        data: Momentová data (torque, angle)
        target_torque: Cílový moment pro výpočet milníků [Nm]

    Returns:
        Slovník s klíči "50%", "90%", "95%", "98%" (úhly dosažení)
        a "stability" (hodnocení stability v pracovní fázi).
    """
    abs_target = abs(target_torque)
    milestones = {"50%": 0.5, "90%": 0.9, "95%": 0.95, "98%": 0.98}

    results: dict = {}
    for label, pct in milestones.items():
        threshold = abs_target * pct
        for torque, angle in data:
            if abs(torque) >= threshold:
                results[label] = f"{abs(angle):.0f}°"
                break
        if label not in results:
            results[label] = "Nedosaženo"

    stable = sum(1 for t, _ in data if abs(abs(t) - abs_target) < 0.01)
    near = sum(1 for t, _ in data if abs(t) >= abs_target * 0.98)
    results["stability"] = (
        "Dobrá" if near > 0 and stable >= near * 0.8 else "Kontroluj PID"
    )

    return results


# ---------------------------------------------------------------------------
# Uložení CSV
# ---------------------------------------------------------------------------

def save_csv(data: List[Tuple[float, float]], filepath: str) -> str:
    """Uloží momentová data do CSV souboru.

    Formát výstupu (neměnný):
        - Oddělovač: ';'
        - Hlavička: 'Torque [Nm]' / 'Angle [°]'
        - Moment: 2 desetinná místa
        - Úhel: celé číslo

    Args:
        data: Momentová data (torque, angle)
        filepath: Cesta k výstupnímu souboru (adresář bude vytvořen)

    Returns:
        Absolutní cesta k uloženému souboru
    """
    dirpath = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dirpath, exist_ok=True)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Torque [Nm]", "Angle [°]"])
        for torque, angle in data:
            writer.writerow([f"{torque:.2f}", f"{angle:.0f}"])

    return os.path.abspath(filepath)
