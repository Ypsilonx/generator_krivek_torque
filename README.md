# Torque Curve Generator

Nástroj pro generování momentových křivek servomotorů ve formátu CSV.
Podporuje více typů náběhu, směrové mapování LH/RH motorů, volitelné
zakončení blokovým momentem a import reálných dat z Excel souborů (.xlsx).

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

Požaduje `matplotlib>=3.5.0` a `openpyxl>=3.1.0`.
Veškerá matematika používá standardní knihovnu (`math`) – numpy není potřeba.

---

## Režimy práce (záložky GUI)

### Záložka „Parametry" – generování konstantní křivky

Klasický režim: definujete cílový moment, délku pracovní fáze, typ náběhu
a volitelný blok. Výstupem je hladká křivka s plochou pracovní fází.

### Záložka „Import XLSX" – reálná data z měření

Načtete Excel soubor s naměřenými hodnotami momentu (sloupec A) a úhlu
(sloupec B). Aplikace:

1. **Automaticky detekuje** hlavičkový řádek
2. **Validuje** každý řádek – hlásí chybějící, nečíselné a duplicitní hodnoty
3. **Detekuje anomálie** – velké mezery v úhlové sekvenci a odlehlé hodnoty momentu (> 3σ)
4. **Nabídne opravu** – tlačítko „Odebrat odlehlé hodnoty" je aktivní při nálezu
5. **Přidá náběh** (volitelný) cílený na první hodnotu importovaných dat – plynulé napojení
6. **Přidá blok** na konci (volitelný, sdílený s oběma záložkami)
7. **Zobrazí graf** okamžitě po načtení souboru

#### Formát vstupního Excel souboru

| Sloupec A | Sloupec B |
|---|---|
| Torque [Nm] | Angle [°] |
| 8.23 | 0 |
| 7.91 | 5 |
| … | … |

- Záhlaví je volitelné (detekuje se automaticky)
- Úhly nemusí začínat od 0 – normalizace se provede automaticky
- Pořadí řádků nemusí být seřazeno – data se seřadí dle úhlu

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

# --- Režim A: konstantní křivka ---
data = engine.generate_curve(
    target_torque=25.0,    # cílový moment [Nm]
    working_degrees=720.0, # pracovní rozsah [°] (2 otáčky)
    ramp_type="hybrid",    # typ náběhu
    ramp_degrees=50.0,     # délka náběhové fáze [°]
    end_with_block=True,   # zakončit blokem?
    block_torque=40.0,     # blokový moment [Nm]
)

# --- Režim B: reálná data z Excelu ---
imported, issues = engine.load_xlsx("mereni.xlsx")
# issues = [{"level": "warning", "message": "...", "count": 3}, ...]

data = engine.generate_curve_from_data(
    imported_data=imported, # data z load_xlsx
    ramp_type="hybrid",
    ramp_degrees=50.0,
    end_with_block=True,
    block_torque=40.0,
)

# --- Společné kroky ---
data = engine.apply_direction_mapping(data, motor_type="LH", direction="CCW")
path = engine.save_csv(data, "output/moje_krivka.csv")
stats = engine.analyze_curve(data, target_torque=25.0)
```

### Veřejné funkce

| Funkce | Popis |
|---|---|
| `generate_curve(...)` | Generuje list `(torque, angle)` dvojic – konstantní pracovní fáze |
| `generate_curve_from_data(...)` | Generuje křivku z importovaných reálných dat |
| `load_xlsx(filepath)` | Načte .xlsx, validuje, normalizuje; vrátí `(data, issues)` |
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
| `_setup_gui()` | Sestavení layoutu včetně scrollovatelného levého panelu a záložek |
| `_create_torque_section()` | Záložka Parametry – konstantní křivka |
| `_create_import_section()` | Záložka Import XLSX – načtení a validace dat |
| `_on_tab_changed()` | Přepínání záložek, obnovení grafu a auto-názvu |
| `_on_*_change()` | Reakce na změnu widgetů |
| `_schedule_chart_refresh()` / `_refresh_chart_live()` | Live preview s debouncing (120 ms) |
| `_refresh_chart_import()` | Live preview pro import mód |
| `_update_chart(..., import_mode)` | Překreslení grafu (parametr `import_mode` přizpůsobí osy) |
| `_save_csv()` | Vstupní bod exportu – větví se dle aktivní záložky |
| `_save_csv_thread()` / `_generate_curve_thread()` | Export konstantní křivky (vlákno) |
| `_save_csv_import_thread()` | Export importované křivky (vlákno) |
| `_load_xlsx_thread()` / `_on_xlsx_loaded()` | Načtení xlsx (vlákno) + zpracování výsledků |
| `_remove_outliers()` | Interaktivní odebrání odlehlých hodnot |

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

Příklad souboru z import módu `import_LH_CCW_hybrid_mereni_vzork.csv`:

```
Torque [Nm];Angle [°]
0.00;0
...
8.23;50
7.91;55
8.47;60
...
40.00;546
40.00;547
40.00;548
```

Náběhová fáze (0 → první naměřená hodnota), poté reálná naměřená data, volitelný blok.

---

## Testování

Prozatím nejsou automatizované testy. Doporučená ruční verifikace:

```powershell
# Smoke test engine vrstvy – konstantní křivka
python -c "
import torque_engine as e
d = e.generate_curve(25.0, 360.0, 'hybrid', 45.0, True, 40.0)
print(f'Bodů: {len(d)}, první: {d[0]}, poslední: {d[-1]}')
d2 = e.apply_direction_mapping(d, 'LH', 'CW')
print(f'Po mapování LH/CW: {d2[100]}')
e.save_csv(d, 'output/test_smoke.csv')
print('CSV OK')
"

# Smoke test – import xlsx
python -c "
import openpyxl, math, torque_engine as e
wb = openpyxl.Workbook(); ws = wb.active
ws.append(['Torque [Nm]', 'Angle [deg]'])
for i in range(50):
    ws.append([round(8.0 + math.sin(i * 0.4), 2), i * 5])
wb.save('output/test_import.xlsx')
data, issues = e.load_xlsx('output/test_import.xlsx')
print(f'Načteno: {len(data)} bodů, issues: {len(issues)}')
curve = e.generate_curve_from_data(data, 'hybrid', 45.0, True, 25.0)
e.save_csv(curve, 'output/test_import_out.csv')
print('Import OK')
"
```

