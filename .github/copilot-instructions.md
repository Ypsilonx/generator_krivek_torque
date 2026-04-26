# Torque Generator Pro - Python CSV Generator

## Architektura projektu

Třívrstvá architektura – každá vrstva má jasně definovanou zodpovědnost:

```
torque_engine.py          ← výpočetní jádro (bez UI závislostí, testovatelné izolovaně)
torque_curve_generator.py ← CLI + wrapper TorqueCurveGenerator pro zpětnou kompatibilitu
torque_gui.py             ← GUI (tkinter + matplotlib), deleguje výpočty na engine
```

## Invarianty – NIKDY neměnit

- **Formát CSV**: oddělovač `;`, hlavička `Torque [Nm];Angle [°]`, moment `{t:.2f}`, úhel `{a:.0f}`
- **Veřejné API `torque_engine`**: funkce `generate_curve`, `apply_direction_mapping`, `analyze_curve`, `save_csv` – signatury jsou stabilní
- **`RAMP_TYPES` tuple** je single source of truth pro platné typy náběhu

## Klíčové implementační detaily

### tkinter / GUI
- Všechny číselné vstupy jsou `tk.DoubleVar` – VŽDY číst přes `self._safe_get(var)`, nikdy přímým `.get()` (způsobuje `TclError` při neúplném vstupu)
- Live preview: `_schedule_chart_refresh()` → debounce 120 ms → `_refresh_chart_live()` → `_update_chart()`
- Ukládání CSV běží v separátním vlákně (`_save_csv_thread` → `_generate_curve_thread`)

### Přidání nového typu náběhu
1. Funkce se signaturou `fn(angle, max_angle, target_torque) -> float` do `torque_engine.py`
2. Klíč do `_RAMP_FUNCTIONS` dict v `torque_engine.py`
3. Klíč do `RAMP_TYPES` tuple v `torque_engine.py`
4. Label do `_RAMP_LABELS` dict v `torque_gui.py`
GUI a CLI si nový typ vyzvednou automaticky.

### Směrové mapování (LH/RH)
- `apply_direction_mapping(data, motor_type, direction)` aplikuje znaménko
- LH+CCW = +, LH+CW = −, RH+CCW = −, RH+CW = +
- Generujte vždy kladná data, mapování aplikujte jako poslední krok

## Stav implementace (duben 2026)

✅ Výpočetní jádro (`torque_engine.py`) – hybrid/exponential/scurve/linear náběh  
✅ CLI wrapper (`torque_curve_generator.py`) – zachována zpětná kompatibilita  
✅ GUI (`torque_gui.py`) – live preview, dark-theme graf, LH/RH mapování  
✅ Dokumentace (`README.md`)  
❌ Automatizované testy – zatím nejsou  

## Připraveno pro rozšíření

Kandidáti na budoucí funkce (schválení uživatelem před implementací):
- Exportní profily / šablony (uložit sadu parametrů)
- Dávkové generování (více křivek najednou)
- Srovnávací graf (více křivek v jednom grafu)
- Importní analýza (načíst existující CSV a zobrazit)
- Automatizované unit testy (`pytest`)
