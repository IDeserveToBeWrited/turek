# skrypt do obliczania vmax skrzyni
# zrobiony przez chatbota
import os
import re

# Ustawienie katalogu bazowego dla wyszukiwania plików .sii
BASE_DIR = "."

# --- Stałe do Obliczenia Prędkości (POPRAWIONE) ---
RPM = 2100.0
# Przyjmujemy Obwód Koła (C) dla typowych opon ciężarówki w ETS2: C = 3.19 metra
C = 3.19 

# Wzór na prędkość (km/h): V = (RPM * C * 60) / (Całkowite Przełożenie * 1000)
# Całkowite Przełożenie = Diff_ratio / Ratio_max (Współczynnik Prędkości)
# Stała_Licznik = RPM * C * 60 / 1000  (Wzór wymaga konwersji metrów na km)
SPEED_CONSTANT_NUMERATOR = RPM * C * 60 / 1000

def get_truck_model(file_path):
    """
    Wydobywa nazwę ciężarówki ze ścieżki pliku, szukając folderu pomiędzy 'truck' a 'transmission'.
    """
    try:
        parts = file_path.lower().replace('\\', '/').split('/')
        if 'truck' in parts and 'transmission' in parts:
            truck_index = parts.index('truck')
            transmission_index = parts.index('transmission')
            # Szukamy folderu pomiędzy 'truck' a 'transmission'
            if transmission_index > truck_index + 1:
                return parts[truck_index + 1]
    except Exception:
        pass
    return "N/A (Sprawdź ścieżkę!)"

def analyze_transmission_files(base_dir):
    """
    Analizuje pliki .sii skrzyń biegów i znajduje tę z największą prędkością.
    """
    results = []

    # Wyrażenia regularne do ekstrakcji danych
    name_re = re.compile(r'accessory_transmission_data\s*:\s*([^.]+)\.')
    diff_ratio_re = re.compile(r'differential_ratio:\s*(\d+\.?\d*)')
    ratios_forward_re = re.compile(r'ratios_forward\[\d+\]:\s*(\d+\.?\d*)')

    for root, _, files in os.walk(base_dir):
        # Sprawdzamy, czy w ścieżce jest 'transmission' (dla optymalizacji)
        if 'transmission' in root.lower() or 'retard.sii' in files: 
            for filename in files:
                if filename.endswith('.sii'):
                    file_path = os.path.join(root, filename)
                    
                    current_name = None
                    diff_ratio = None
                    max_ratio_forward = 0.0 # Najniższa wartość przełożenia

                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()

                            name_match = name_re.search(content)
                            if name_match:
                                # Używamy nazwy pliku i części przed '.volvo...'
                                current_name = f"{filename} ({name_match.group(1)})"
                            else:
                                current_name = filename
                            
                            diff_match = diff_ratio_re.search(content)
                            if diff_match:
                                diff_ratio = float(diff_match.group(1))

                            ratios_matches = ratios_forward_re.findall(content)
                            if ratios_matches:
                                # Najniższa wartość z ratios_forward to najwyższy bieg
                                max_ratio_forward = min(float(r) for r in ratios_matches)
                            
                            speed_factor = None
                            theoretical_speed = None
                            
                            if diff_ratio is not None and max_ratio_forward > 0.0:
                                # Współczynnik prędkości = Diff_ratio / Max_Ratio_Forward
                                speed_factor = diff_ratio / max_ratio_forward
                                
                                # Obliczenie PRĘDKOŚCI TEORETYCZNEJ (km/h) - POPRAWIONE
                                # V = Stała_Licznik / Współczynnik Prędkości
                                theoretical_speed = SPEED_CONSTANT_NUMERATOR / speed_factor

                                truck_model = get_truck_model(file_path)
                                
                                results.append({
                                    'name': current_name,
                                    'truck_model': truck_model,
                                    'diff_ratio': diff_ratio,
                                    'max_ratio_forward': max_ratio_forward,
                                    'speed_factor': speed_factor,
                                    'theoretical_speed': theoretical_speed,
                                    'path': file_path
                                })
                                    
                    except Exception as e:
                        print(f"Błąd podczas przetwarzania pliku {file_path}: {e}")

    return results

# Wywołanie funkcji
all_results = analyze_transmission_files(BASE_DIR)

print("--- 🚛 POPRAWIONA Analiza Skrzyń Biegów ETS2 ---")
print(f"Obroty silnika do porównania (RPM): **{RPM:.0f}**")
print(f"Założony obwód koła: **{C} metra**.")
print("Pamiętaj: Teoretyczna prędkość może się nieznacznie różnić od rzeczywistej w grze ze względu na opory powietrza, tarcie i małe różnice w modelach kół.")

if all_results:
    # Sortowanie wyników (od najszybszej do najwolniejszej)
    sorted_results = sorted(all_results, key=lambda x: x['speed_factor'])
    
    print("\n## 📊 Wyniki Analizy Skrzyń Biegów (od najszybszej do najwolniejszej):")
    
    # Nagłówki tabeli
    header = "{:<50} | {:<25} | {:<10} | {:<10} | {:<15}"
    separator = "-" * 115
    
    print(header.format("Nazwa Skrzyni (Plik / Model)", "Model Ciężarówki", "Dyfer", "Bieg Max", "Prędkość (km/h)"))
    print(separator)
    
    # Wiersze danych
    for r in sorted_results:
        # Ograniczamy prędkość do 300 km/h, bo wyższe wartości są nierealne
        speed_display = r['theoretical_speed'] #if r['theoretical_speed'] < 300 else 300
        
        print(header.format(
            r['name'], 
            r['truck_model'], 
            f"{r['diff_ratio']:.2f}", 
            f"{r['max_ratio_forward']:.2f}", 
            f"**{speed_display:.2f}**"
        ))

    best = sorted_results[0]
    print("\n--- Zwycięzca (Najniższy Współczynnik Prędkości) ---")
    print(f"Największą prędkość teoretyczną (przy {RPM:.0f} RPM) osiągnie skrzynia:")
    print(f"* **Nazwa:** {best['name']}")
    print(f"* **Model Ciężarówki:** {best['truck_model']}")
    print(f"* **Obliczona Prędkość:** **{best['theoretical_speed']:.2f} km/h**")
    print(f"* **Współczynnik Prędkości (Diff Ratio / Max Ratio):** {best['speed_factor']:.4f}")
    
else:
    print("\nNie znaleziono żadnych plików transmission/*.sii do analizy w podanym katalogu bazowym.")