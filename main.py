import os
import shutil
import tempfile
import librosa
import numpy as np
import yt_dlp
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
from scipy.ndimage import median_filter

app = FastAPI(title="Arpegia API")

def get_chord_templates():
    """Genera plantillas de chroma para diversos tipos de acordes en las 12 tonalidades."""
    chord_types = {
        '':      [0, 4, 7],           # Mayor
        'm':     [0, 3, 7],           # Menor
        '7':     [0, 4, 7, 10],       # Dominante 7
    }
    
    roots = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    templates = {}
    
    for r_idx, root in enumerate(roots):
        for suffix, intervals in chord_types.items():
            template = np.zeros(12)
            for interval in intervals:
                template[(r_idx + interval) % 12] = 1.0
            
            if np.linalg.norm(template) > 0:
                template /= np.linalg.norm(template)
                
            templates[f"{root}{suffix}"] = template
            
    return templates

CHORD_TEMPLATES = get_chord_templates()

def detect_chords(audio_path):
    y, sr = librosa.load(audio_path, sr=22050)
    
    y_harmonic, y_percussive = librosa.effects.hpss(y)
    
    tempo, beat_frames = librosa.beat.beat_track(y=y_percussive, sr=sr)
    
    chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr)
    
    chroma_synced = librosa.util.sync(chroma, beat_frames, aggregate=np.median)
    
    template_names = list(CHORD_TEMPLATES.keys())
    template_matrix = np.array(list(CHORD_TEMPLATES.values()))
    
    similarities = np.dot(template_matrix, chroma_synced)
    best_indices = np.argmax(similarities, axis=0)
    
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    
    chords_sequence = []
    last_chord = None
    
    for i, best_idx in enumerate(best_indices):
        current_chord = template_names[best_idx]
        
        if current_chord != last_chord:
            time_val = float(beat_times[i]) if i < len(beat_times) else float(beat_times[-1])
            
            chords_sequence.append({
                "timestamp": round(time_val, 2),
                "chord": current_chord
            })
            last_chord = current_chord
            
    return chords_sequence

def get_spotify_metadata(url: str):
    """Extrae metadatos básicos de una URL de Spotify sin API Key."""
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Buscamos el título de Open Graph
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title["content"]
            # En Spotify, el título suele ser "Song Name - Single by Artist" o similar
            return title.split(" - single")[0].split(" | Spotify")[0]
        
        return soup.title.string.split(" - song")[0] if soup.title else None
    except Exception:
        return None

@app.get("/")
def read_root():
    return {"mensaje": "¡Arpegia API con soporte YouTube/Spotify está funcionando!"}

@app.post("/analizar-acordes/")
async def analizar_acordes(audio: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        shutil.copyfileobj(audio.file, tmp)
        tmp_path = tmp.name
    
    try:
        acordes = detect_chords(tmp_path)
        return {"archivo": audio.filename, "acordes": acordes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

class UrlRequest(BaseModel):
    url: str

@app.post("/analizar-url/")
async def analizar_url(request: UrlRequest):
    search_query = request.url
    is_spotify = "spotify.com" in request.url
    
    if is_spotify:
        metadata = get_spotify_metadata(request.url)
        if not metadata:
            raise HTTPException(status_code=400, detail="No se pudieron extraer metadatos de Spotify")
        search_query = f"ytsearch1:{metadata} audio"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': tempfile.gettempdir() + '/%(id)s.%(ext)s',
        'noplaylist': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Si es Spotify, search_query es un término de búsqueda, no una URL directa
            info = ydl.extract_info(search_query, download=True)
            
            # Si fue una búsqueda, info['entries'] contiene el resultado
            if 'entries' in info:
                info = info['entries'][0]
                
            audio_path = os.path.join(tempfile.gettempdir(), f"{info['id']}.mp3")
            
        acordes = detect_chords(audio_path)
        
        if os.path.exists(audio_path):
            os.remove(audio_path)
            
        return {
            "titulo": info.get('title'), 
            "acordes": acordes,
            "origen": "Spotify" if is_spotify else "YouTube"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
