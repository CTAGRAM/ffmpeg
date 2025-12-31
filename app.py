"""
FFmpeg API Service for Koyeb Free Tier
Handles: Trim, Concat, Audio Merge, Subtitles
Optimized for 256MB RAM / 0.1 vCPU
"""

from flask import Flask, request, jsonify, send_file
import subprocess
import os
import uuid
import requests
import shutil
from functools import wraps
import time
import threading

app = Flask(__name__)

# Configuration
WORK_DIR = "/tmp/ffmpeg_work"
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB limit
API_KEY = os.environ.get("FFMPEG_API_KEY", "your-secret-key")
CLOUDFLARE_R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY", "")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "ffmpeg-outputs")

# Ensure work directory exists
os.makedirs(WORK_DIR, exist_ok=True)


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
    """Remove files older than 10 minutes"""
    now = time.time()
    for filename in os.listdir(WORK_DIR):
        filepath = os.path.join(WORK_DIR, filename)
        if os.path.isfile(filepath):
            if now - os.path.getmtime(filepath) > 600:  # 10 minutes
                os.remove(filepath)


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
        return None
    
    try:
        import boto3
        s3 = boto3.client(
            's3',
            endpoint_url=CLOUDFLARE_R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY
        )
        s3.upload_file(filepath, R2_BUCKET, filename)
        return f"{CLOUDFLARE_R2_ENDPOINT}/{R2_BUCKET}/{filename}"
    except Exception as e:
        print(f"R2 upload error: {e}")
        return None


def run_ffmpeg(cmd, timeout=300):
    """Run FFmpeg command with timeout"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode == 0, result.stderr
    except subprocess.TimeoutExpired:
        return False, "FFmpeg timeout"
    except Exception as e:
        return False, str(e)


# ==================== HEALTH CHECK ====================

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    # Check FFmpeg is available
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    ffmpeg_ok = result.returncode == 0
    
    return jsonify({
        "status": "healthy" if ffmpeg_ok else "degraded",
        "ffmpeg": ffmpeg_ok,
        "work_dir": os.path.exists(WORK_DIR),
        "disk_free_mb": shutil.disk_usage(WORK_DIR).free // (1024 * 1024)
    })


# ==================== TRIM VIDEO ====================

@app.route("/trim", methods=["POST"])
@require_api_key
def trim_video():
    """
    Trim video to specified duration
    
    POST /trim
    {
        "video_url": "https://...",
        "duration": 5,
        "start": 0  // optional
    }
    """
    cleanup_old_files()
    
    data = request.json
    video_url = data.get("video_url")
    duration = data.get("duration", 5)
    start = data.get("start", 0)
    
    if not video_url:
        return jsonify({"error": "video_url required"}), 400
    
    job_id = str(uuid.uuid4())[:8]
    input_path = os.path.join(WORK_DIR, f"{job_id}_input.mp4")
    output_path = os.path.join(WORK_DIR, f"{job_id}_trimmed.mp4")
    
    try:
        # Download video
        download_file(video_url, input_path)
        
        # FFmpeg trim with stream copy (fast, no re-encoding)
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", input_path,
            "-t", str(duration),
            "-c", "copy",  # No re-encoding = fast + low memory
            "-avoid_negative_ts", "make_zero",
            output_path
        ]
        
        success, error = run_ffmpeg(cmd)
        
        if not success:
            return jsonify({"error": f"FFmpeg failed: {error}"}), 500
        
        # Upload to R2 if configured
        r2_url = upload_to_r2(output_path, f"trimmed_{job_id}.mp4")
        
        if r2_url:
            os.remove(input_path)
            os.remove(output_path)
            return jsonify({"url": r2_url, "job_id": job_id})
        
        # Return file directly if no R2
        return send_file(output_path, mimetype="video/mp4", as_attachment=True)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Cleanup input file
        if os.path.exists(input_path):
            os.remove(input_path)


# ==================== CONCAT VIDEOS ====================

@app.route("/concat", methods=["POST"])
@require_api_key
def concat_videos():
    """
    Concatenate multiple videos
    
    POST /concat
    {
        "video_urls": ["https://...", "https://..."],
        "trim_duration": 5  // optional, trim each video first
    }
    """
    cleanup_old_files()
    
    data = request.json
    video_urls = data.get("video_urls", [])
    trim_duration = data.get("trim_duration")
    
    if len(video_urls) < 2:
        return jsonify({"error": "At least 2 video URLs required"}), 400
    
    if len(video_urls) > 20:
        return jsonify({"error": "Maximum 20 videos allowed"}), 400
    
    job_id = str(uuid.uuid4())[:8]
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
                os.remove(input_path)
                input_files.append(trimmed_path)
            else:
                input_files.append(input_path)
        
        # Create concat list file
        with open(concat_list_path, 'w') as f:
            for filepath in input_files:
                f.write(f"file '{filepath}'\n")
        
        # FFmpeg concat with stream copy
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            output_path
        ]
        
        success, error = run_ffmpeg(cmd, timeout=600)
        
        if not success:
            return jsonify({"error": f"FFmpeg failed: {error}"}), 500
        
        # Upload to R2
        r2_url = upload_to_r2(output_path, f"concat_{job_id}.mp4")
        
        if r2_url:
            return jsonify({"url": r2_url, "job_id": job_id})
        
        return send_file(output_path, mimetype="video/mp4", as_attachment=True)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Cleanup
        for f in input_files:
            if os.path.exists(f):
                os.remove(f)
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)


# ==================== MERGE AUDIO ====================

@app.route("/merge-audio", methods=["POST"])
@require_api_key
def merge_audio():
    """
    Merge audio track with video
    
    POST /merge-audio
    {
        "video_url": "https://...",
        "audio_url": "https://...",
        "shortest": true  // trim to shortest stream
    }
    """
    cleanup_old_files()
    
    data = request.json
    video_url = data.get("video_url")
    audio_url = data.get("audio_url")
    shortest = data.get("shortest", True)
    
    if not video_url or not audio_url:
        return jsonify({"error": "video_url and audio_url required"}), 400
    
    job_id = str(uuid.uuid4())[:8]
    video_path = os.path.join(WORK_DIR, f"{job_id}_video.mp4")
    audio_path = os.path.join(WORK_DIR, f"{job_id}_audio.mp3")
    output_path = os.path.join(WORK_DIR, f"{job_id}_merged.mp4")
    
    try:
        # Download files
        download_file(video_url, video_path)
        download_file(audio_url, audio_path)
        
        # FFmpeg merge audio
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",  # No video re-encoding
            "-c:a", "aac",
            "-b:a", "128k"  # Lower bitrate for memory efficiency
        ]
        
        if shortest:
            cmd.append("-shortest")
        
        cmd.append(output_path)
        
        success, error = run_ffmpeg(cmd)
        
        if not success:
            return jsonify({"error": f"FFmpeg failed: {error}"}), 500
        
        # Upload to R2
        r2_url = upload_to_r2(output_path, f"merged_{job_id}.mp4")
        
        if r2_url:
            return jsonify({"url": r2_url, "job_id": job_id})
        
        return send_file(output_path, mimetype="video/mp4", as_attachment=True)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        for f in [video_path, audio_path]:
            if os.path.exists(f):
                os.remove(f)


# ==================== ADD SUBTITLES ====================

@app.route("/add-subtitles", methods=["POST"])
@require_api_key
def add_subtitles():
    """
    Add subtitles/text overlay to video
    
    POST /add-subtitles
    {
        "video_url": "https://...",
        "subtitles": [
            {"text": "Species Name", "start": 0, "end": 5, "position": "bottom"},
            {"text": "Period Info", "start": 0, "end": 5, "position": "top"}
        ],
        "font_size": 24,
        "font_color": "white"
    }
    
    ⚠️ WARNING: This requires re-encoding and uses more resources!
    Consider using 720p or lower resolution for free tier.
    """
    cleanup_old_files()
    
    data = request.json
    video_url = data.get("video_url")
    subtitles = data.get("subtitles", [])
    font_size = data.get("font_size", 24)
    font_color = data.get("font_color", "white")
    
    if not video_url:
        return jsonify({"error": "video_url required"}), 400
    
    job_id = str(uuid.uuid4())[:8]
    video_path = os.path.join(WORK_DIR, f"{job_id}_video.mp4")
    ass_path = os.path.join(WORK_DIR, f"{job_id}_subs.ass")
    output_path = os.path.join(WORK_DIR, f"{job_id}_subtitled.mp4")
    
    try:
        # Download video
        download_file(video_url, video_path)
        
        # Generate ASS subtitle file
        ass_content = generate_ass_file(subtitles, font_size, font_color)
        with open(ass_path, 'w') as f:
            f.write(ass_content)
        
        # FFmpeg with subtitle burn-in
        # Using lower preset for memory efficiency
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"ass={ass_path}",
            "-c:v", "libx264",
            "-preset", "ultrafast",  # Fast encoding, lower memory
            "-crf", "28",  # Lower quality = faster/less memory
            "-c:a", "copy",
            "-threads", "1",  # Limit threads for low memory
            output_path
        ]
        
        success, error = run_ffmpeg(cmd, timeout=600)
        
        if not success:
            return jsonify({"error": f"FFmpeg failed: {error}"}), 500
        
        # Upload to R2
        r2_url = upload_to_r2(output_path, f"subtitled_{job_id}.mp4")
        
        if r2_url:
            return jsonify({"url": r2_url, "job_id": job_id})
        
        return send_file(output_path, mimetype="video/mp4", as_attachment=True)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        for f in [video_path, ass_path]:
            if os.path.exists(f):
                os.remove(f)


def generate_ass_file(subtitles, font_size, font_color):
    """Generate ASS subtitle file from subtitle list"""
    
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
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Bottom,Arial,{font_size},{color_code},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,30,1
Style: Top,Arial,{font_size},{color_code},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,8,10,10,30,1
Style: Center,Arial,{font_size},{color_code},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,5,10,10,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    events = []
    for sub in subtitles:
        text = sub.get("text", "")
        start = format_ass_time(sub.get("start", 0))
        end = format_ass_time(sub.get("end", 5))
        position = sub.get("position", "bottom").capitalize()
        
        # Escape special characters
        text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        
        events.append(f"Dialogue: 0,{start},{end},{position},,0,0,0,,{text}")
    
    return ass_header + "\n".join(events)


def format_ass_time(seconds):
    """Convert seconds to ASS time format (H:MM:SS.cc)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"


# ==================== FULL PIPELINE ====================

@app.route("/process-evolution", methods=["POST"])
@require_api_key
def process_evolution():
    """
    Complete evolution video pipeline
    
    POST /process-evolution
    {
        "video_urls": ["https://...", ...],
        "audio_url": "https://...",
        "species_data": [
            {"name": "Species 1", "period": "Cambrian", "mya": 500},
            ...
        ],
        "trim_duration": 5,
        "add_text": true
    }
    
    This combines: trim → concat → audio → subtitles (optional)
    """
    cleanup_old_files()
    
    data = request.json
    video_urls = data.get("video_urls", [])
    audio_url = data.get("audio_url")
    species_data = data.get("species_data", [])
    trim_duration = data.get("trim_duration", 5)
    add_text = data.get("add_text", False)
    
    if len(video_urls) < 1:
        return jsonify({"error": "At least 1 video URL required"}), 400
    
    job_id = str(uuid.uuid4())[:8]
    
    try:
        # Step 1: Download and trim all videos
        trimmed_files = []
        for i, url in enumerate(video_urls):
            input_path = os.path.join(WORK_DIR, f"{job_id}_input_{i}.mp4")
            trimmed_path = os.path.join(WORK_DIR, f"{job_id}_trim_{i}.mp4")
            
            download_file(url, input_path)
            
            trim_cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-t", str(trim_duration),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                trimmed_path
            ]
            run_ffmpeg(trim_cmd)
            os.remove(input_path)
            trimmed_files.append(trimmed_path)
        
        # Step 2: Concatenate
        concat_list_path = os.path.join(WORK_DIR, f"{job_id}_concat.txt")
        concat_output = os.path.join(WORK_DIR, f"{job_id}_concat.mp4")
        
        with open(concat_list_path, 'w') as f:
            for filepath in trimmed_files:
                f.write(f"file '{filepath}'\n")
        
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            concat_output
        ]
        run_ffmpeg(concat_cmd)
        
        # Cleanup trimmed files
        for f in trimmed_files:
            os.remove(f)
        os.remove(concat_list_path)
        
        # Step 3: Add audio (if provided)
        if audio_url:
            audio_path = os.path.join(WORK_DIR, f"{job_id}_audio.mp3")
            audio_output = os.path.join(WORK_DIR, f"{job_id}_with_audio.mp4")
            
            download_file(audio_url, audio_path)
            
            audio_cmd = [
                "ffmpeg", "-y",
                "-i", concat_output,
                "-i", audio_path,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "128k",
                "-shortest",
                audio_output
            ]
            run_ffmpeg(audio_cmd)
            
            os.remove(concat_output)
            os.remove(audio_path)
            final_output = audio_output
        else:
            final_output = concat_output
        
        # Step 4: Add text overlays (if requested)
        # ⚠️ This is heavy - skipped by default
        if add_text and species_data:
            subtitles = []
            for i, species in enumerate(species_data):
                start_time = i * trim_duration
                end_time = start_time + trim_duration
                subtitles.append({
                    "text": species.get("name", f"Species {i+1}"),
                    "start": start_time,
                    "end": end_time,
                    "position": "bottom"
                })
                if species.get("period"):
                    subtitles.append({
                        "text": f"{species.get('period')} - {species.get('mya', '?')} MYA",
                        "start": start_time,
                        "end": end_time,
                        "position": "top"
                    })
            
            ass_path = os.path.join(WORK_DIR, f"{job_id}_subs.ass")
            text_output = os.path.join(WORK_DIR, f"{job_id}_final.mp4")
            
            ass_content = generate_ass_file(subtitles, 24, "white")
            with open(ass_path, 'w') as f:
                f.write(ass_content)
            
            text_cmd = [
                "ffmpeg", "-y",
                "-i", final_output,
                "-vf", f"ass={ass_path}",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                "-c:a", "copy",
                "-threads", "1",
                text_output
            ]
            success, error = run_ffmpeg(text_cmd, timeout=900)
            
            if success:
                os.remove(final_output)
                os.remove(ass_path)
                final_output = text_output
        
        # Upload to R2
        r2_url = upload_to_r2(final_output, f"evolution_{job_id}.mp4")
        
        if r2_url:
            os.remove(final_output)
            return jsonify({
                "url": r2_url,
                "job_id": job_id,
                "videos_processed": len(video_urls),
                "audio_added": bool(audio_url),
                "text_added": add_text
            })
        
        return send_file(final_output, mimetype="video/mp4", as_attachment=True)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== MAIN ====================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
