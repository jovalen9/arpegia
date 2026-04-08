from fastapi import FastAPI, File, UploadFile

# Inicializamos la aplicación
app = FastAPI()

# Ruta de prueba para saber si el servidor está vivo
@app.get("/")
def leer_raiz():
    return {"mensaje": "¡El servidor de acordes está vivo!"}

# Ruta donde Flutter enviará el archivo de audio
@app.post("/analizar-acordes/")
async def analizar_acordes(audio: UploadFile = File(...)):
    # ---------------------------------------------------------
    # Aquí es donde, en el futuro, pondremos el código de Librosa 
    # o Madmom para analizar el archivo de audio real.
    # ---------------------------------------------------------
    
    # Por ahora, simulamos una respuesta exitosa
    return {
        "archivo_recibido": audio.filename,
        "acordes_simulados": ["C", "G", "Am", "F"],
        "estado": "Éxito"
    }