"""
FFmpeg API Service for Koyeb Free Tier
Handles: Trim, Concat, Audio Merge, Subtitles
Optimized for 256MB RAM / 0.1 vCPU
NOW ASYNCHRONOUS to prevent timeouts
"""

from flask import Flask, request, jsonify
import subprocess
import os
import uuid
import requests
import shutil
from functools import wraps
import time
import threading
from datetime import datetime

app = Flask(__name__)

# Configuration
WORK_DIR = "/tmp/ffmpeg_work"
API_KEY = os.environ.get("FFMPEG_API_KEY", "your-secret-key")
CLOUDFLARE_R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY", "")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "ffmpeg-outputs")

# Ensure work directory exists
os.makedirs(WORK_DIR, exist_ok=True)

# In-memory job store (since we have one instance)
JOBS = {}

def require_api_key(f):
    """Simple API key authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if key != API_KEY:
            return jsonify({"error": "Invalid API key"}), 401
        return f(*args, **kwargs)
    return decorated

def cleanup_old_files():
    """Remove files older than 10 minutes and old jobs"""
    now = time.time()
    # clean files
    for filename in os.listdir(WORK_DIR):
        filepath = os.path.join(WORK_DIR, filename)
        if os.path.isfile(filepath):
            if now - os.path.getmtime(filepath) > 600:  # 10 minutes
                try:
                    os.remove(filepath)
                except:
                    pass
    
    # clean jobs older than 1 hour
    job_ids = list(JOBS.keys())
    for jid in job_ids:
        if now - JOBS[jid]['created_at'] > 3600:
            del JOBS[jid]

def download_file(url, filepath):
    """Download file from URL with streaming"""
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with open(filepath, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return filepath

def upload_to_r2(filepath, filename):
    """Upload file to Cloudflare R2"""
    if not CLOUDFLARE_R2_ENDPOINT:
        print("R2 Not configured")
        return None
    
    try:
        import boto3
        session = boto3.Session()
        s3 = session.client(
            's3',
            endpoint_url=CLOUDFLARE_R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY
        )
        s3.upload_file(filepath, R2_BUCKET, filename)
        # Construct public URL (assuming public bucket access or worker)
        # If R2_PUBLIC_URL env var is set, use it
        public_url_base = os.environ.get("R2_PUBLIC_URL", f"{CLOUDFLARE_R2_ENDPOINT}/{R2_BUCKET}")
        return f"{public_url_base}/{filename}"
    except Exception as e:
        print(f"R2 upload error: {e}")
        return None

def run_ffmpeg(cmd, timeout=900):
    """Run FFmpeg command with timeout"""
    try:
        print(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode != 0:
            print(f"FFmpeg Error: {result.stderr}")
        return result.returncode == 0, result.stderr
    except subprocess.TimeoutExpired:
        return False, "FFmpeg timeout"
    except Exception as e:
        return False, str(e)

# ==================== ASYNC WORKER ====================

def update_job(job_id, status, result=None, error=None):
    if job_id in JOBS:
        JOBS[job_id]['status'] = status
        if result:
            JOBS[job_id]['result'] = result
        if error:
            JOBS[job_id]['error'] = error
        JOBS[job_id]['updated_at'] = time.time()

def worker_wrapper(job_id, func, **kwargs):
    """Executes the function and updates job status"""
    try:
        update_job(job_id, 'processing')
        result = func(job_id, **kwargs)
        if result and isinstance(result, dict) and 'url' in result:
             update_job(job_id, 'completed', result=result)
        else:
             # Should not happen if func returns dict with url, else it raised exception
             update_job(job_id, 'failed', error="Unknown error, no URL returned")
    except Exception as e:
        print(f"Job {job_id} failed: {e}")
        update_job(job_id, 'failed', error=str(e))

def start_async_job(func, **kwargs):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        'status': 'queued',
        'created_at': time.time(),
        'updated_at': time.time(),
        'type': func.__name__
    }
    thread = threading.Thread(target=worker_wrapper, args=(job_id, func), kwargs=kwargs)
    thread.start()
    return job_id

# ==================== WORKER FUNCTIONS ====================

def do_concat_videos(job_id, video_urls, trim_duration):
    input_files = []
    concat_list_path = os.path.join(WORK_DIR, f"{job_id}_concat.txt")
    output_path = os.path.join(WORK_DIR, f"{job_id}_concat.mp4")
    
    try:
        # Download all videos
        for i, url in enumerate(video_urls):
            input_path = os.path.join(WORK_DIR, f"{job_id}_input_{i}.mp4")
            download_file(url, input_path)
            
            # Optionally trim each video
            if trim_duration:
                trimmed_path = os.path.join(WORK_DIR, f"{job_id}_trimmed_{i}.mp4")
                trim_cmd = [
                    "ffmpeg", "-y",
                    "-i", input_path,
                    "-t", str(trim_duration),
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    trimmed_path
                ]
                run_ffmpeg(trim_cmd)
                os.remove(input_path) # clean input
                input_files.append(trimmed_path)
            else:
                input_files.append(input_path)
        
        # Create concat list file
        with open(concat_list_path, 'w') as f:
            for filepath in input_files:
                f.write(f"file '{filepath}'\n")
        
        # FFmpeg concat
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            output_path
        ]
        
        success, error = run_ffmpeg(cmd, timeout=900)
        if not success:
            raise Exception(f"FFmpeg concat failed: {error}")
        
        # Upload to R2
        r2_url = upload_to_r2(output_path, f"concat_{job_id}.mp4")
        if not r2_url:
            raise Exception("Failed to upload to R2")
            
        return {"url": r2_url}
        
    finally:
        # Cleanup
        for f in input_files:
            if os.path.exists(f): os.remove(f)
        if os.path.exists(concat_list_path): os.remove(concat_list_path)
        if os.path.exists(output_path): os.remove(output_path)

def do_merge_audio(job_id, video_url, audio_url, shortest):
    video_path = os.path.join(WORK_DIR, f"{job_id}_video.mp4")
    audio_path = os.path.join(WORK_DIR, f"{job_id}_audio.mp3")
    output_path = os.path.join(WORK_DIR, f"{job_id}_merged.mp4")
    
    try:
        download_file(video_url, video_path)
        download_file(audio_url, audio_path)
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k"
        ]
        if shortest:
            cmd.append("-shortest")
        cmd.append(output_path)
        
        success, error = run_ffmpeg(cmd)
        if not success:
            raise Exception(f"FFmpeg merge failed: {error}")
            
        r2_url = upload_to_r2(output_path, f"merged_{job_id}.mp4")
        if not r2_url:
            raise Exception("Failed to upload to R2")
            
        return {"url": r2_url}
    finally:
        for f in [video_path, audio_path, output_path]:
            if os.path.exists(f): os.remove(f)

def do_add_subtitles(job_id, video_url, subtitles, font_size, font_color):
    video_path = os.path.join(WORK_DIR, f"{job_id}_video.mp4")
    ass_path = os.path.join(WORK_DIR, f"{job_id}_subs.ass")
    output_path = os.path.join(WORK_DIR, f"{job_id}_subtitled.mp4")
    
    try:
        download_file(video_url, video_path)
        
        ass_content = generate_ass_file(subtitles, font_size, font_color)
        with open(ass_path, 'w') as f:
            f.write(ass_content)
            
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"ass={ass_path}",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "copy",
            "-threads", "1",
            output_path
        ]
        
        success, error = run_ffmpeg(cmd, timeout=900)
        if not success:
            raise Exception(f"FFmpeg subtitle failed: {error}")
            
        r2_url = upload_to_r2(output_path, f"subtitled_{job_id}.mp4")
        if not r2_url:
            raise Exception("Failed to upload to R2")
            
        return {"url": r2_url}
    finally:
        for f in [video_path, ass_path, output_path]:
            if os.path.exists(f): os.remove(f)

def generate_ass_file(subtitles, font_size, font_color):
    # Color mapping
    colors = {
        "white": "&H00FFFFFF",
        "black": "&H00000000",
        "yellow": "&H0000FFFF",
        "red": "&H000000FF",
        "green": "&H0000FF00",
        "blue": "&H00FF0000"
    }
    color_code = colors.get(font_color, "&H00FFFFFF")
    
    ass_header = f"""[Script Info]
Title: Generated Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},{color_code},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for sub in subtitles:
        text = sub.get("text", "")
        start = format_ass_time(sub.get("start", 0))
        end = format_ass_time(sub.get("end", 5))
        
        # Determine alignment based on 'position' ('top', 'bottom', 'center')
        # Alignment: 2=Bottom, 8=Top, 5=Center
        pos_map = {'bottom': 2, 'top': 8, 'center': 5}
        align = pos_map.get(sub.get('position', 'bottom').lower(), 2)
        
        # Escape special characters
        text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        
        # Override alignment if needed: {\\an8}
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\an{align}}}{text}")
    
    return ass_header + "\n".join(events)

def format_ass_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

# ==================== ENDPOINTS ====================

@app.route("/health", methods=["GET"])
def health():
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    ffmpeg_ok = result.returncode == 0
    return jsonify({
        "status": "healthy" if ffmpeg_ok else "degraded",
        "ffmpeg": ffmpeg_ok,
        "active_jobs": len([j for j in JOBS.values() if j['status'] == 'processing']),
        "disk_free_mb": shutil.disk_usage(WORK_DIR).free // (1024 * 1024)
    })

@app.route("/tasks/<job_id>", methods=["GET"])
@require_api_key
def get_task(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

@app.route("/concat", methods=["POST"])
@require_api_key
def concat_videos():
    cleanup_old_files()
    data = request.json
    video_urls = data.get("video_urls", [])
    trim_duration = data.get("trim_duration")
    
    if len(video_urls) < 2:
        return jsonify({"error": "At least 2 video URLs required"}), 400
    
    job_id = start_async_job(do_concat_videos, video_urls=video_urls, trim_duration=trim_duration)
    return jsonify({"job_id": job_id, "status": "queued"}), 202

@app.route("/merge-audio", methods=["POST"])
@require_api_key
def merge_audio():
    cleanup_old_files()
    data = request.json
    video_url = data.get("video_url")
    audio_url = data.get("audio_url")
    shortest = data.get("shortest", True)
    
    if not video_url or not audio_url:
        return jsonify({"error": "video_url and audio_url required"}), 400
        
    job_id = start_async_job(do_merge_audio, video_url=video_url, audio_url=audio_url, shortest=shortest)
    return jsonify({"job_id": job_id, "status": "queued"}), 202

@app.route("/add-subtitles", methods=["POST"])
@require_api_key
def add_subtitles():
    cleanup_old_files()
    data = request.json
    video_url = data.get("video_url")
    subtitles = data.get("subtitles", [])
    font_size = data.get("font_size", 24)
    font_color = data.get("font_color", "white")
    
    if not video_url:
        return jsonify({"error": "video_url required"}), 400
        
    job_id = start_async_job(do_add_subtitles, video_url=video_url, subtitles=subtitles, font_size=font_size, font_color=font_color)
    return jsonify({"job_id": job_id, "status": "queued"}), 202

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
