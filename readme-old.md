mattermost/ (Aquí vive el clon del repositorio de Mattermost) 

blocks/ (Tus scripts funcionales para B3 a B9) 

results/ (Donde se guardan los JSONs generados) 

ui/ (Tu código de react) 
Deja exactamente como están los siguientes archivos y carpetas, ya que son el motor que hace funcionar a React:

    node_modules/

    public/

    main.jsx

    package.json y package-lock.json

    vite.config.js

    eslint.config.js e index.html

main.py (Tu orquestador principal) 

seed.py (Tu script de inyección de datos)


volume_backup_1: Estado base tras ejecutar seed.py (admin test, usuario víctima, equipo, canal).

volume_backup_2: Estado tras inyectar payloads XSS.

Recordá siempre el flujo obligatorio para restaurar:

    Detener: docker compose stop.

    Limpiar y Reemplazar: Borrar el contenido de volumes/db y pegar el backup deseado.

    Reanudar: docker compose up -d.

Gemini:
- prompt para guardar cada chat: "Concisely state all important facts, decisions, and context from our chat so far so that a different AI chat thread can continue this conversation without any gap in necessary knowledge."

- guardar en un .txt

- importar en otro chat: This is the context from our previous session. Let's continue working on..."
levantar back: .venv\Scripts\uvicorn.exe api:app --reload --port 8000
levantar front: bun run dev

Nota sobre el Bloque 6 (Revisión Humana): La pausa en el pipeline durante esta etapa es estrictamente intencional y no un proceso automatizado. Constituye el núcleo del argumento académico del enfoque híbrido : la IA se encarga de reducir el espacio de búsqueda y generar los payloads contextualizados, pero es el criterio técnico humano quien decide el riesgo real y prioriza la ejecución, eliminando los falsos positivos antes del análisis dinámico