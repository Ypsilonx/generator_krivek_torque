# Torque Curve Generator

Nástroj pro generování momentových křivek servomotorů ve formátu CSV.
Podporuje více typů náběhu, směrové mapování LH/RH motorů a volitelné
zakončení blokovým momentem.

---

## Architektura

```
torque_engine.py          ← výpočetní jádro (bez UI závislostí)
torque_curve_generator.py ← CLI aplikace + wrapper pro zpětnou kompatibilitu
torque_gui.py             ← GUI aplikace s live matplotlib vizualizací
output/                   ← výchozí složka pro generované CSV soubory
```

**Pravidlo**: veškerá matematika žije výhradně v `torque_engine.py`.
Ostatní moduly ji pouze volají – nikdy neduplikují.

---

## Rychlý start

```powershell
# Aktivace prostředí
.\.venv\Scripts\Activate.ps1

# GUI aplikace (doporučeno)
python torque_gui.py

# CLI aplikace
python torque_curve_generator.py
```

### Závislosti

```
pip install -r requirements.txt
```

Požaduje pouze `matplotlib>=3.5.0`. Veškerá matematika používá standardní
knihovnu (`math`) – numpy není potřeba.

---

## Typy náběhu

| Identifikátor | Popis | Doporučené použití |
|---|---|---|
| `hybrid` | Exp (0–40 %) → lineární (40–80 %) → S-křivka (80–100 %) | PID regulace – výchozí volba |
| `exponential` | Exp náběh + sigmoid dosednutí | Tam kde záleží na rychlosti dosažení momentu |
| `scurve` | Čistý tanh – nejhladší průběh | Citlivé aplikace, přesná poloha |
| `linear` | Konstantní rychlost nárůstu | Jednoduché testovací scénáře |

---

## Směrové mapování

| Motor | Směr | Znaménko |
|---|---|---|
| LH | CCW | + |
| LH | CW  | − |
| RH | CCW | − |
| RH | CW  | + |

Kladné hodnoty momentu i úhlu = pohyb v souhlasném směru.
Záporné hodnoty signalizují opačný směr otáčení.

---

## Formát CSV (neměnný)

```
Torque [Nm];Angle [°]
2.50;1
5.00;2
...
```

- Oddělovač: `;`
- Záhlaví: `Torque [Nm];Angle [°]`
- Moment: 2 desetinná místa (`{t:.2f}`)
- Úhel: celé číslo (`{a:.0f}`)
- Kódování: UTF-8

> **Varování**: Formát CSV nesmí být změněn – výstup je konzumován externími systémy.

---

## API – `torque_engine`

Primární vstupní bod pro programové použití:

```python
import torque_engine as engine

# Vygenerování křivky
data = engine.generate_curve(
    target_torque=25.0,    # cílový moment [Nm]
    working_degrees=720.0, # pracovní rozsah [°] (2 otáčky)
    ramp_type="hybrid",    # typ náběhu
    ramp_degrees=50.0,     # délka náběhové fáze [°]
    end_with_block=True,   # zakončit blokem?
    block_torque=40.0,     # blokový moment [Nm]
)

# Aplikace směrového mapování
data = engine.apply_direction_mapping(data, motor_type="LH", direction="CCW")

# Uložení do CSV
path = engine.save_csv(data, "output/moje_krivka.csv")

# Analýza milníků
stats = engine.analyze_curve(data, target_torque=25.0)
# → {"50%": 22.0, "90%": 41.0, "95%": 44.0, "98%": 47.0, "stability": "Velmi stabilní"}
```

### Veřejné funkce

| Funkce | Popis |
|---|---|
| `generate_curve(...)` | Generuje list `(torque, angle)` dvojic po 1° |
| `apply_direction_mapping(data, motor_type, direction)` | Aplikuje znaménko dle konvence LH/RH |
| `analyze_curve(data, target_torque)` | Milníky 50/90/95/98 % a hodnocení stability |
| `save_csv(data, filepath)` | Zapíše CSV, vytvoří složky, vrátí abs. cestu |
| `hybrid_ramp(angle, max_angle, target)` | Přímý přístup k náběhové funkci |
| `exponential_ramp(...)` | viz výše |
| `scurve_ramp(...)` | viz výše |
| `linear_ramp(...)` | viz výše |

### Konstanty

```python
engine.RAMP_TYPES  # ("hybrid", "exponential", "scurve", "linear")
```

---

## Přidání nového typu náběhu

1. Implementujte funkci se signaturou `fn(angle, max_angle, target_torque) -> float` v `torque_engine.py`
2. Přidejte klíč do `_RAMP_FUNCTIONS` ve stejném souboru
3. Přidejte klíč do `RAMP_TYPES` (tuple – zachovejte pořadí)
4. Přidejte popisný label do `_RAMP_LABELS` v `torque_gui.py`

GUI a CLI si nový typ náběhu vyzvednou automaticky – žádné další změny nejsou potřeba.

---

## Přidání nové funkce do GUI

Třída `TorqueCurveGeneratorGUI` v `torque_gui.py` je organizována do sekcí:

| Sekce metod | Účel |
|---|---|
| `_setup_gui()` a `_build_*()` | Sestavení widgetů |
| `_on_*_change()` | Reakce na změnu widgetů |
| `_setup_auto_update_callbacks()` | Registrace trace callbacků |
| `_schedule_chart_refresh()` / `_refresh_chart_live()` | Live preview s debouncing |
| `_update_chart()` | Překreslení matplotlib grafu |
| `_save_csv()` / `_save_csv_thread()` / `_generate_curve_thread()` | Export do souboru |
| `_analyze_and_show()` | Výpočet milníků a zobrazení výsledků |

**Tkinter proměnné**: všechny vstupní hodnoty jsou uloženy jako `tk.DoubleVar` / `tk.StringVar` /
`tk.BooleanVar`. Čtěte je vždy přes `self._safe_get(var)` – nikdy přímým `.get()` na `DoubleVar`
(způsobuje `TclError` při neúplném vstupu).

---

## Struktura výstupního souboru

Příklad vygenerovaného souboru `torque_LH_CCW_hybrid_25Nm_2rot.csv`:

```
Torque [Nm];Angle [°]
0.00;0
1.23;1
...
25.00;50
25.00;51
...
40.00;771
40.00;772
40.00;773
```

Poslední 3 řádky jsou blokový moment (pokud je aktivní).

---

## Testování

Prozatím nejsou automatizované testy. Doporučená ruční verifikace:

```powershell
# Smoke test engine vrstvy
python -c "
import torque_engine as e
d = e.generate_curve(25.0, 360.0, 'hybrid', 45.0, True, 40.0)
print(f'Bodů: {len(d)}, první: {d[0]}, poslední: {d[-1]}')
d2 = e.apply_direction_mapping(d, 'LH', 'CW')
print(f'Po mapování LH/CW: {d2[100]}')
e.save_csv(d, 'output/test_smoke.csv')
print('CSV OK')
"
```
