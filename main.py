import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fresh", "restore"], default="fresh") #para verificar que el flujo sea funcional desde el primer momento
    args = parser.parse_args()

    if args.mode == "fresh":
        print("Iniciando modo Clean Run (Reglamentario)...")
        # Aquí llamarías a los comandos de limpieza y seed
    else:
        print("Iniciando modo Fast Dev (Snapshots)...")
        # Aquí llamarías a la función de reemplazar la carpeta /db