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
- **Veřejné API `torque_engine`**: funkce `generate_curve`, `generate_curve_from_data`, `load_xlsx`, `apply_direction_mapping`, `analyze_curve`, `save_csv` – signatury jsou stabilní
- **`RAMP_TYPES` tuple** je single source of truth pro platné typy náběhu

## Klíčové implementační detaily

### tkinter / GUI
- Všechny číselné vstupy jsou `tk.DoubleVar` – VŽDY číst přes `self._safe_get(var)`, nikdy přímým `.get()` (způsobuje `TclError` při neúplném vstupu)
- Live preview: `_schedule_chart_refresh()` → debounce 120 ms → `_refresh_chart_live()` → větví se dle `_active_tab` → `_update_chart(import_mode=...)`
- Ukládání CSV běží v separátním vlákně: parametrický mód `_save_csv_thread` → `_generate_curve_thread`; import mód `_save_csv_import_thread`
- Levý panel je scrollovatelný Canvas – všechny widgety jdou do vnitřního `left` Frame, ne přímo do `left_outer`
- GUI má dvě záložky (`ttk.Notebook`): „Parametry" (konstantní křivka) a „Import XLSX" (reálná data)
- `_active_tab` (int 0/1) určuje aktuální záložku – větvení v `_save_csv`, `_refresh_chart_live`, `_generate_auto_filename`

### Import XLSX workflow
- `engine.load_xlsx(path)` → vrátí `(data, issues)` – data normalizovaná na 0°, seřazená dle úhlu
- `engine.generate_curve_from_data(imported_data, ...)` → náběh cílí na PRVNÍ hodnotu importu (plynulé napojení)
- Výsledky validace: level `info` / `warning` / `error`; klíč `outlier_indices` u odlehlých hodnot
- Tlačítko „Odebrat odlehlé hodnoty" se aktivuje pouze když `_outlier_indices` není prázdný

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
✅ Import reálných dat (`torque_engine.load_xlsx` + `generate_curve_from_data`)  
✅ Validace a detekce anomálií v importovaných datech (3σ, mezery, duplicity)  
✅ CLI wrapper (`torque_curve_generator.py`) – zachována zpětná kompatibilita  
✅ GUI (`torque_gui.py`) – dvě záložky, scrollovatelný panel, live preview, dark-theme graf, LH/RH mapování  
✅ Dokumentace (`README.md`)  
❌ Automatizované testy – zatím nejsou  

## Připraveno pro rozšíření

Kandidáti na budoucí funkce (schválení uživatelem před implementací):
- Exportní profily / šablony (uložit sadu parametrů)
- Dávkové generování (více křivek najednou)
- Srovnávací graf (více křivek v jednom grafu)
- Automatizované unit testy (`pytest`)
