#!/usr/bin/env python3
"""
Torque Curve Generator - CLI aplikace pro generování momentových křivek.

TorqueCurveGenerator je tenký wrapper nad torque_engine, který zachovává
původní veřejné API pro zpětnou kompatibilitu.
CLI rozhraní v main() je zachováno beze změny.
"""

import os
from typing import List, Tuple

import torque_engine as engine


class TorqueCurveGenerator:
    """Generátor momentových křivek – wrapper nad torque_engine.

    Deleguje veškeré výpočty na torque_engine a přidává pohodlné
    metody pro práci s výstupní složkou.
    """

    def __init__(self, output_folder: str = "output"):
        """
        Args:
            output_folder: Cesta ke složce pro výstupní CSV soubory
        """
        self.output_folder = output_folder
        os.makedirs(self.output_folder, exist_ok=True)

    def generate_torque_curve(
        self,
        target_torque: float,
        working_degrees: float,
        ramp_type: str = "hybrid",
        ramp_degrees: float = 45.0,
        end_with_block: bool = False,
        block_torque: float = 50.0,
    ) -> List[Tuple[float, float]]:
        """Generuje momentovou křivku. Deleguje na torque_engine.generate_curve.

        Args:
            target_torque: Cílový pracovní moment [Nm]
            working_degrees: Pracovní úhel [°]
            ramp_type: Typ náběhu ("hybrid", "exponential", "scurve", "linear")
            ramp_degrees: Úhel pro dosažení stability [°]
            end_with_block: Ukončit blokem
            block_torque: Moment pro blok [Nm]

        Returns:
            List tuplesů (torque, angle)
        """
        return engine.generate_curve(
            target_torque, working_degrees, ramp_type,
            ramp_degrees, end_with_block, block_torque,
        )

    def save_csv(self, data: List[Tuple[float, float]], filename: str) -> str:
        """Uloží data do CSV ve výstupní složce. Deleguje na torque_engine.save_csv.

        Args:
            data: Momentová data (torque, angle)
            filename: Název souboru bez přípony .csv

        Returns:
            Absolutní cesta k uloženému souboru
        """
        filepath = os.path.join(self.output_folder, f"{filename}.csv")
        return engine.save_csv(data, filepath)

    def analyze_curve(
        self, data: List[Tuple[float, float]], target_torque: float
    ) -> dict:
        """Analyzuje rychlost dosažení cílového momentu. Deleguje na torque_engine.

        Args:
            data: Momentová data (torque, angle)
            target_torque: Cílový moment [Nm]

        Returns:
            Slovník s milníky a hodnocením stability
        """
        return engine.analyze_curve(data, target_torque)


def main():
    """Hlavní aplikace pro generování momentových křivek."""
    
    generator = TorqueCurveGenerator()
    
    print("=" * 50)
    print("    TORQUE CURVE GENERATOR")
    print("    Optimalizováno pro PID regulaci")
    print("=" * 50)
    print()
    
    while True:
        try:
            print("🎯 PARAMETRY MOMENTOVÉ KŘIVKY")
            print("-" * 30)
            
            # Základní parametry
            target_torque = float(input("Cílový pracovní moment [Nm]: "))
            
            print("\nZadání pracovního rozsahu:")
            print("1. Počet otáček (např. 5 otáček)")
            print("2. Úhel ve stupních (např. 1800°)")
            
            range_type = input("Způsob zadání (1/2): ").strip()
            
            if range_type == "1":
                rotations = float(input("Počet pracovních otáček: "))
                working_degrees = rotations * 360
                range_desc = f"{rotations} otáček"
            else:
                working_degrees = float(input("Pracovní úhel [°]: "))
                range_desc = f"{working_degrees}°"
            
            print(f"   → Pracovní rozsah: {range_desc} ({working_degrees}°)")
            
            # Náběhový typ
            print(f"\n🚀 TYP NÁBĚHU (pro minimalizaci kmitů PID)")
            print("-" * 40)
            print("1. Hybridní (DOPORUČENO) - rychlý + stabilní")
            print("2. Exponenciální - velmi rychlý náběh")  
            print("3. S-křivka - nejhladší, bez overshootu")
            print("4. Lineární - klasický přístup")
            
            ramp_choice = input("Vyberte typ náběhu (1-4): ").strip()
            ramp_types = {"1": "hybrid", "2": "exponential", "3": "scurve", "4": "linear"}
            ramp_type = ramp_types.get(ramp_choice, "hybrid")
            
            # Délka náběhu
            ramp_degrees = float(input(f"Úhel pro dosažení stability [°] (doporučeno 30-50): "))
            
            if ramp_degrees >= working_degrees:
                print("⚠️  Varování: Náběh je delší než pracovní rozsah!")
            
            # Blokování
            print(f"\n🛑 UKONČENÍ SEKVENCE")
            print("-" * 20)
            end_with_block = input("Ukončit blokem (tvrdé zastavení)? (y/n): ").lower().startswith('y')
            
            block_torque = 50.0
            if end_with_block:
                block_torque = float(input("Moment pro blok [Nm]: "))
            
            # Generování křivky
            print(f"\n⚙️  Generuji momentovou křivku...")
            print(f"   • Typ náběhu: {ramp_type}")
            print(f"   • Cílový moment: {target_torque} Nm")
            print(f"   • Náběh do: {ramp_degrees}°")
            print(f"   • Pracovní rozsah: {working_degrees}°")
            if end_with_block:
                print(f"   • Blok: {block_torque} Nm")
            
            # Generování dat
            data = generator.generate_torque_curve(
                target_torque, working_degrees, ramp_type, 
                ramp_degrees, end_with_block, block_torque
            )
            
            # Analýza křivky
            analysis = generator.analyze_curve(data, target_torque)
            
            print(f"\n📊 ANALÝZA NÁBĚHU")
            print("-" * 18)
            for milestone, angle in analysis.items():
                if milestone != "stability":
                    print(f"   • {milestone} cíle: {angle}")
            print(f"   • Stabilita: {analysis['stability']}")
            
            # Název souboru
            filename = input(f"\nNázev souboru (bez přípony): ").strip()
            if not filename:
                block_suffix = f"_blok{block_torque:.0f}" if end_with_block else ""
                filename = f"torque_{ramp_type}_{target_torque:.0f}Nm_{working_degrees:.0f}deg{block_suffix}"
            
            # Uložení
            csv_path = generator.save_csv(data, filename)
            
            print(f"\n✅ VÝSLEDEK")
            print("-" * 10)
            print(f"📁 CSV soubor: {csv_path}")
            print(f"📊 Celkem bodů: {len(data)}")
            print(f"📈 Rozsah úhlů: 0° → {data[-1][1]:.0f}°")
            print(f"🎯 Formát: 2 sloupce, ; oddělovač")
            print(f"   - Torque: 2 des. místa")
            print(f"   - Úhel: po 1°")
            
            # Ukázka dat
            show_preview = input(f"\nZobrazit náhled dat? (y/n): ").lower().startswith('y')
            if show_preview:
                print(f"\n📋 NÁHLED (prvních 10 řádků):")
                print("Torque [Nm] | Angle [°]")
                print("-" * 22)
                for i, (torque, angle) in enumerate(data[:10]):
                    print(f"{torque:10.2f} | {angle:7.0f}")
                if len(data) > 10:
                    print(f"... a dalších {len(data)-10} řádků")
            
            # Pokračovat?
            print()
            if not input("Generovat další křivku? (y/n): ").lower().startswith('y'):
                break
            
            print("\n" + "="*50 + "\n")
            
        except ValueError as e:
            print(f"❌ Chyba: Neplatná hodnota - {e}")
            print()
        except KeyboardInterrupt:
            print(f"\n\nUkončeno uživatelem.")
            break
        except Exception as e:
            print(f"❌ Chyba: {e}")
            print()
    
    print(f"\n🎉 Děkuji za použití Torque Curve Generator!")
    print(f"📁 Všechny soubory jsou v složce: {generator.output_folder}/")


if __name__ == "__main__":
    main()
