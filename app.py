import os
import time
import requests
import subprocess
import uuid
import threading
import json
import logging
import sqlite3
import shutil
from flask import Flask, request, jsonify, g

app = Flask(__name__)

# --- Configuration ---
FFMPEG_API_KEY = os.environ.get("FFMPEG_API_KEY", "ffmpeg_sk_9a7b3c2e1f4d8a6b5c3e7f2a1b9d4c8e")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
R2_BUCKET = os.environ.get("R2_BUCKET")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "https://pub-879b72d29274423bab4fd53b5946501d.r2.dev")
DB_PATH = "/tmp/jobs.db"  # Use /tmp as it is likely writable and preserved on worker restart (but not deploy)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# --- Database Setup ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at REAL,
                updated_at REAL,
                type TEXT,
                result TEXT,
                error TEXT
            )
        ''')

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Initialize DB on startup
try:
    init_db()
except Exception as e:
    logger.error(f"Failed to initialize DB: {e}")

# --- Helper Functions ---

def update_job(job_id, status, result=None, error=None):
    """Updates job status in SQLite"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            update_fields = ["status = ?", "updated_at = ?"]
            params = [status, time.time()]
            
            if result:
                update_fields.append("result = ?")
                params.append(json.dumps(result))
            
            if error:
                update_fields.append("error = ?")
                params.append(str(error))
            
            params.append(job_id)
            
            query = f"UPDATE jobs SET {', '.join(update_fields)} WHERE id = ?"
            conn.execute(query, params)
            logger.info(f"Job {job_id} updated to {status}")
    except Exception as e:
        logger.error(f"Failed to update job {job_id}: {e}")

def get_job_from_db(job_id):
    """Retrieves job from SQLite"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            if row:
                job = dict(row)
                if job['result']:
                    try:
                        job['result'] = json.loads(job['result'])
                    except:
                        pass
                return job
            return None
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        return None

def run_ffmpeg(cmd, timeout=300, job_id=None):
    """
    Run FFmpeg command with timeout and log to file to save RAM.
    Avoids capture_output=True which causes OOM on large outputs.
    """
    job_part_id = uuid.uuid4().hex[:6]
    log_file_path = f"/tmp/ffmpeg_{job_id}_{job_part_id}.log"
    try:
        logger.info(f"Running command: {' '.join(cmd)}")
        
        # Redirect stdout/stderr to a file instead of memory
        with open(log_file_path, "w") as f:
            result = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT, # Merge stderr into stdout
                timeout=timeout
            )
        
        if result.returncode != 0:
            # Read only the last 1KB of logs for error reporting
            try:
                with open(log_file_path, "r") as f:
                    f.seek(0, 2) # Seek to end
                    size = f.tell()
                    f.seek(max(size - 1024, 0)) # Go back 1KB
                    error_log = f.read()
            except Exception as read_err:
                error_log = f"Could not read log file: {read_err}"
            
            logger.error(f"FFmpeg Error (tail): {error_log}")
            return False, f"FFmpeg exited with code {result.returncode}. Log tail: {error_log}"
            
        return True, None
        
    except subprocess.TimeoutExpired:
        return False, "FFmpeg timeout"
    except Exception as e:
        return False, str(e)
    finally:
        # Cleanup log file to prevent filling up /tmp
        if os.path.exists(log_file_path):
            try:
                os.remove(log_file_path)
            except:
                pass

def upload_to_r2(file_path, object_name):
    """Uploads a file to Cloudflare R2 using boto3"""
    import boto3
    from botocore.exceptions import NoCredentialsError

    if not all([R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET]):
        return None, "R2 configuration missing"

    s3_client = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY
    )

    try:
        s3_client.upload_file(file_path, R2_BUCKET, object_name)
        # Construct public URL
        url = f"{R2_PUBLIC_URL}/{object_name}"
        return url, None
    except NoCredentialsError:
        return None, "Credentials not available"
    except Exception as e:
        return None, str(e)

# --- Async Worker Logic ---

def worker_wrapper(job_id, func, **kwargs):
    """Executes the function and updates job status"""
    try:
        update_job(job_id, 'processing')
        result_url = func(job_id, **kwargs) # Pass job_id to func
        
        if result_url:
             update_job(job_id, 'completed', result={'url': result_url})
        else:
             # If func returns None but didn't raise exception (shouldn't happen with current logic)
             update_job(job_id, 'failed', error="No URL returned")
             
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        update_job(job_id, 'failed', error=str(e))

def start_async_job(func, **kwargs):
    job_id = str(uuid.uuid4())
    
    # Insert initial job record directly into DB before thread starts
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO jobs (id, status, created_at, updated_at, type) VALUES (?, ?, ?, ?, ?)",
                (job_id, 'queued', time.time(), time.time(), func.__name__)
            )
    except Exception as e:
        logger.error(f"Failed to create job record: {e}")
        return None

    # Start background thread
    thread = threading.Thread(target=worker_wrapper, args=(job_id, func), kwargs=kwargs)
    thread.daemon = True 
    thread.start()
    
    return job_id

# --- Core Logic Functions ---

def download_file(url, local_path):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return local_path

def logic_concat(job_id, video_urls, trim_duration):
    work_dir = f"/tmp/ffmpeg_work/{job_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    try:
        # 1. Download and Trim
        trimmed_files = []
        for i, url in enumerate(video_urls):
            input_path = os.path.join(work_dir, f"input_{i}.mp4")
            download_file(url, input_path)
            
            trimmed_path = os.path.join(work_dir, f"trimmed_{i}.mp4")
            
            # Use 'make_zero' to reset timestamps prevent sync issues
            # Using copy for speed; if this fails or OOMs, we might need to re-encode (slow)
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-t", str(trim_duration),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                trimmed_path
            ]
            
            success, error = run_ffmpeg(cmd, job_id=job_id)
            if not success:
                raise Exception(f"Trim failed for video {i}: {error}")
            
            trimmed_files.append(trimmed_path)

        # 2. Create Concat List
        list_path = os.path.join(work_dir, "list.txt")
        with open(list_path, "w") as f:
            for path in trimmed_files:
                f.write(f"file '{path}'\n")

        # 3. Concatenate (using copy mode since all videos from same AI source)
        output_filename = f"concat_{uuid.uuid4().hex}.mp4"
        output_path = os.path.join(work_dir, output_filename)
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            output_path
        ]
        
        success, error = run_ffmpeg(cmd, job_id=job_id)
        if not success:
             raise Exception(f"Concat failed: {error}")

        # 4. Upload
        url, error = upload_to_r2(output_path, output_filename)
        if error:
            raise Exception(f"Upload failed: {error}")
            
        return url
        
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

def logic_merge_audio(job_id, video_url, audio_url, shortest):
    work_dir = f"/tmp/ffmpeg_work/{job_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    try:
        video_path = os.path.join(work_dir, "input_video.mp4")
        audio_path = os.path.join(work_dir, "input_audio.mp3")
        output_filename = f"merged_{uuid.uuid4().hex}.mp4"
        output_path = os.path.join(work_dir, output_filename)
        
        download_file(video_url, video_path)
        download_file(audio_url, audio_path)
        
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0"
        ]
        
        if shortest:
            cmd.append("-shortest")
            
        cmd.append(output_path)
        
        success, error = run_ffmpeg(cmd, job_id=job_id)
        if not success: raise Exception(f"Merge failed: {error}")
        
        url, error = upload_to_r2(output_path, output_filename)
        if error: raise Exception(f"Upload failed: {error}")
        return url

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

def logic_add_subtitles(job_id, video_url, subtitle_content, format):
    work_dir = f"/tmp/ffmpeg_work/{job_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    try:
        video_path = os.path.join(work_dir, "input_video.mp4")
        output_filename = f"subtitled_{uuid.uuid4().hex}.mp4"
        output_path = os.path.join(work_dir, output_filename)
        
        download_file(video_url, video_path)
        
        # Write subtitle file
        ext = "ass" if format == "ass" else "srt"
        sub_path = os.path.join(work_dir, f"subs.{ext}")
        
        # Debug: log first part of subtitle content
        logger.info(f"Subtitle content preview (first 500 chars): {subtitle_content[:500]}")
        logger.info(f"Subtitle content length: {len(subtitle_content)} characters")
        
        with open(sub_path, "w") as f:
            f.write(subtitle_content)
            
        # Hardcode subtitles with memory optimization
        # Use ultrafast preset, limit threads, and CRF for lower memory usage
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"subtitles={sub_path}",
            "-c:v", "libx264",
            "-preset", "ultrafast",  # Fastest encoding = less memory
            "-crf", "23",  # Constant quality mode
            "-threads", "2",  # Limit threads to reduce memory
            "-c:a", "copy",
            output_path
        ]
        
        success, error = run_ffmpeg(cmd, timeout=600, job_id=job_id)  # Increased timeout
        if not success: raise Exception(f"Subtitle burn failed: {error}")
        
        url, error = upload_to_r2(output_path, output_filename)
        if error: raise Exception(f"Upload failed: {error}")
        return url

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# --- API Endpoints ---

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "ffmpeg-api-async-sqlite"}), 200

def require_api_key(func):
    def wrapper(*args, **kwargs):
        if request.headers.get("X-API-Key") != FFMPEG_API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

@app.route("/tasks/<job_id>", methods=["GET"])
@require_api_key
def get_task(job_id):
    job = get_job_from_db(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(dict(job)) # Convert Row to dict

@app.route("/concat", methods=["POST"])
@require_api_key
def schedule_concat():
    data = request.json
    video_urls = data.get("video_urls")
    trim_duration = data.get("trim_duration", 5)
    
    if not video_urls:
        return jsonify({"error": "Missing video_urls"}), 400

    job_id = start_async_job(logic_concat, video_urls=video_urls, trim_duration=trim_duration)
    if not job_id:
         return jsonify({"error": "Failed to start job"}), 500
         
    return jsonify({"job_id": job_id, "status": "queued"}), 202

@app.route("/merge-audio", methods=["POST"])
@require_api_key
def schedule_merge_audio():
    data = request.json
    video_url = data.get("video_url")
    audio_url = data.get("audio_url")
    shortest = data.get("shortest", False)
    
    if not video_url or not audio_url:
        return jsonify({"error": "Missing video_url or audio_url"}), 400

    job_id = start_async_job(logic_merge_audio, video_url=video_url, audio_url=audio_url, shortest=shortest)
    return jsonify({"job_id": job_id, "status": "queued"}), 202

@app.route("/add-subtitles", methods=["POST"])
@require_api_key
def schedule_add_subtitles():
    data = request.json
    video_url = data.get("video_url")
    subtitle_content = data.get("subtitle_content")
    fmt = data.get("format", "srt")
    
    if not video_url or not subtitle_content:
        return jsonify({"error": "Missing video_url or subtitle_content"}), 400

    job_id = start_async_job(logic_add_subtitles, video_url=video_url, subtitle_content=subtitle_content, format=fmt)
    return jsonify({"job_id": job_id, "status": "queued"}), 202

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
