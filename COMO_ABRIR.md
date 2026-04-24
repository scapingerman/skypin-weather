# Cómo abrir este proyecto (no está “solo en el chat”)

Los archivos están en **esta carpeta** en tu PC:

`C:\Users\Usuario\Documents\Claude\Projects\Skyping Weather\skyping-weather`

## En Cursor / VS Code

1. **File → Open Folder…** (Abrir carpeta)
2. Elegí exactamente la carpeta **`skyping-weather`** (la que tiene `docker-compose.yml` adentro).
   - No alcanza con abrir solo `Skyping Weather` si no ves el `docker-compose.yml` en la raíz del explorador.

## Levantar el MVP

En PowerShell:

```powershell
cd "C:\Users\Usuario\Documents\Claude\Projects\Skyping Weather\skyping-weather"
docker compose up --build
```

- Frontend: http://localhost:5173  
- API docs: http://localhost:8000/docs  

## Si el puerto 8000 ya lo usa otro proyecto

Pará el otro stack o cambiá el mapeo en `docker-compose.yml` (por ejemplo `8001:8000`) y ajustá `VITE_API_URL` del frontend a ese puerto.

## Sin Docker (dos terminales)

**Backend:**

```powershell
cd "...\skyping-weather\backend"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend** (sin variable, usa proxy de Vite a `localhost:8000`):

```powershell
cd "...\skyping-weather\frontend"
npm install
npm run dev
```

Opcional: creá `frontend\.env` con:

`VITE_API_URL=http://localhost:8000/api/v1`
