# skrypt do obliczania vmax skrzyni
# zrobiony przez chatbota
import os
import re

# Ustawienie katalogu bazowego dla wyszukiwania plików .sii
BASE_DIR = "."

# --- Stałe do Obliczenia Prędkości (POPRAWIONE) ---
RPM = 2000.0  # Maksymalne obroty silnika
# Przyjmujemy Obwód Koła (C)
C = 3.09  # Obwód koła w metrach

# Stała_Licznik = RPM * C * 60 / 1000
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
    Analizuje pliki .sii skrzyń biegów.
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
                    max_ratio_forward = 0.0

                    try:
                        # Używamy UTF-8 do odczytu dla kompatybilności
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()

                            name_match = name_re.search(content)
                            if name_match:
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
                                speed_factor = diff_ratio * max_ratio_forward
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

def output_results(all_results, RPM, C):
    """
    Generuje wyniki, zapisuje do wynik.txt (UTF-8) i wyświetla w konsoli,
    dodając pustą kolumnę "Zmierzona V (km/h)".
    """
    output = []
    
    # 1. Nagłówki
    output.append("--- 🚛 POPRAWIONA Analiza Skrzyń Biegów ETS2 ---")
    output.append(f"Obroty silnika do porównania (RPM): {RPM:.0f}")
    output.append(f"Założony obwód koła: {C} metra.")
    output.append("Pamiętaj: Teoretyczna prędkość może się nieznacznie różnić od rzeczywistej w grze ze względu na opory powietrza, tarcie i małe różnice w modelach kół.")

    if all_results:
        # Sortowanie wyników (od najszybszej do najwolniejszej)
        sorted_results = sorted(all_results, key=lambda x: x['speed_factor'])
        
        output.append("\n## 📊 Wyniki Analizy Skrzyń Biegów (od najszybszej do najwolniejszej):")
        
        # Nagłówki tabeli (Poszerzone)
        # +17 znaków na nową kolumnę
        header = "{:<50} | {:<25} | {:<10} | {:<10} | {:<15} | {:<18}"
        separator = "-" * 135
        
        output.append(header.format("Nazwa Skrzyni (Plik / Model)", "Model Ciężarówki", "Dyfer", "Bieg Max", "Prędkość (km/h)", "Zmierzona V (km/h)"))
        output.append(separator)
        
        # Wiersze danych
        for r in sorted_results:
            speed_display = r['theoretical_speed'] 
            
            # Dodanie pustego miejsca dla kolumny "Zmierzona V"
            output.append(header.format(
                r['name'], 
                r['truck_model'], 
                f"{r['diff_ratio']:.2f}", 
                f"{r['max_ratio_forward']:.2f}", 
                f"{speed_display:.2f}", 
                "" # Pusta kolumna do ręcznego wypełnienia
            ))

        best = sorted_results[0]
        output.append("\n--- Zwycięzca (Najniższy Współczynnik Prędkości) ---")
        output.append(f"Największą prędkość teoretyczną (przy {RPM:.0f} RPM) osiągnie skrzynia:")
        output.append(f"* Nazwa: {best['name']}")
        output.append(f"* Model Ciężarówki: {best['truck_model']}")
        output.append(f"* Obliczona Prędkość: {best['theoretical_speed']:.2f} km/h")
        output.append(f"* Współczynnik Prędkości (Diff Ratio / Max Ratio): {best['speed_factor']:.4f}")
        
    else:
        output.append("\nNie znaleziono żadnych plików transmission/*.sii do analizy w podanym katalogu bazowym.")
        
    final_output = "\n".join(output)
    
    # Wyświetlenie w konsoli
    console_output = final_output.replace('Prędkość:', '**Prędkość:**').replace('Obliczona Prędkość:', '**Obliczona Prędkość:**')
    print(console_output.replace('{speed_display:.2f}', '**{speed_display:.2f}**'))
    
    # Zapis do pliku wynik.txt z poprawnym kodowaniem UTF-8
    try:
        # Usuwamy pogrubienia (**) na potrzeby czystego pliku tekstowego
        cleaned_output = final_output.replace('**', '')
        with open('wynik.txt', 'w', encoding='utf-8') as f:
            f.write(cleaned_output)
        print("\n--- ZAPISANO ---")
        print("Wyniki analizy zostały zapisane do pliku: wynik.txt (kodowanie UTF-8)")
    except Exception as e:
        print(f"\nBłąd podczas zapisywania do pliku wynik.txt: {e}")

# Wywołanie funkcji
all_results = analyze_transmission_files(BASE_DIR)
output_results(all_results, RPM, C)