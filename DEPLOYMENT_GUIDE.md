# 🚀 FFmpeg API Service - Koyeb Free Tier Deployment Guide

## Overview

This guide deploys a fully functional FFmpeg API service on Koyeb's free tier that handles:
- ✅ Video trimming (stream copy - fast)
- ✅ Video concatenation (stream copy - fast)
- ✅ Audio merging (audio encoding only)
- ⚠️ Subtitle/text overlay (requires re-encoding - slow)
- ✅ Complete evolution video pipeline

---

## 📋 Prerequisites

1. **GitHub account** (for code hosting)
2. **Koyeb account** (free at [koyeb.com](https://koyeb.com))
3. **Cloudflare R2 account** (optional, for output storage)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         n8n Workflow                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FFmpeg API (Koyeb)                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   /trim     │  │  /concat    │  │/merge-audio │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────────────────────────────────────────┐           │
│  │          /process-evolution (full pipeline)     │           │
│  └─────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Cloudflare R2 (output storage)                     │
│                   $0 egress fees                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
ffmpeg-service/
├── app.py              # Main Flask application
├── Dockerfile          # Docker configuration
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

---

## 🚀 Step-by-Step Deployment

### Step 1: Create GitHub Repository

1. Go to [github.com/new](https://github.com/new)
2. Name it `ffmpeg-api-service`
3. Make it **Public** (or Private with Koyeb access)
4. Clone locally:

```bash
git clone https://github.com/YOUR_USERNAME/ffmpeg-api-service.git
cd ffmpeg-api-service
```

### Step 2: Add Project Files

Copy these files to your repository:
- `app.py`
- `Dockerfile`
- `requirements.txt`

```bash
# Add all files
git add .
git commit -m "Initial FFmpeg API service"
git push origin main
```

### Step 3: Create Koyeb Account

1. Go to [koyeb.com](https://app.koyeb.com/)
2. Sign up with GitHub (recommended for easy deployment)
3. Complete verification

### Step 4: Deploy to Koyeb

#### Option A: One-Click Deploy (Easiest)

1. Go to Koyeb Dashboard
2. Click **Create Service**
3. Select **GitHub**
4. Connect your GitHub account
5. Select your `ffmpeg-api-service` repository
6. Configure:

| Setting | Value |
|---------|-------|
| **Branch** | main |
| **Builder** | Dockerfile |
| **Instance Type** | Free (nano) |
| **Regions** | Select closest to you |

7. Add Environment Variables:

| Variable | Value |
|----------|-------|
| `FFMPEG_API_KEY` | `your-secret-key-here` |
| `PORT` | `8000` |

8. Click **Deploy**

#### Option B: Koyeb CLI

```bash
# Install Koyeb CLI
curl -fsSL https://raw.githubusercontent.com/koyeb/koyeb-cli/master/install.sh | bash

# Login
koyeb login

# Deploy
koyeb app create ffmpeg-api \
  --git github.com/YOUR_USERNAME/ffmpeg-api-service \
  --git-branch main \
  --instance-type free \
  --ports 8000:http \
  --routes /:8000 \
  --env FFMPEG_API_KEY=your-secret-key-here \
  --env PORT=8000
```

### Step 5: Get Your API URL

After deployment, Koyeb provides a URL like:
```
https://ffmpeg-api-YOUR_ID.koyeb.app
```

Save this URL - you'll use it in n8n!

---

## ☁️ Setting Up Cloudflare R2 (Recommended)

Without R2, the service returns files directly (slower, may timeout).
With R2, files are uploaded and a URL is returned (faster, more reliable).

### Step 1: Create R2 Bucket

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Navigate to **R2**
3. Click **Create bucket**
4. Name: `ffmpeg-outputs`
5. Click **Create**

### Step 2: Create API Token

1. Go to **R2** → **Manage R2 API Tokens**
2. Click **Create API Token**
3. Permissions: **Object Read & Write**
4. Specify bucket: `ffmpeg-outputs`
5. Click **Create API Token**
6. Save:
   - Access Key ID
   - Secret Access Key
   - Endpoint URL (like `https://xxxxx.r2.cloudflarestorage.com`)

### Step 3: Add R2 to Koyeb Environment

Go to your Koyeb service → **Settings** → **Environment Variables**:

| Variable | Value |
|----------|-------|
| `R2_ENDPOINT` | `https://xxxxx.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY` | Your Access Key ID |
| `R2_SECRET_KEY` | Your Secret Access Key |
| `R2_BUCKET` | `ffmpeg-outputs` |

Click **Save** and **Redeploy**

### Step 4: Make Bucket Public (Optional)

To serve videos directly from R2:

1. Go to R2 bucket → **Settings**
2. Enable **Public Access**
3. Note the public URL: `https://pub-xxxxx.r2.dev`

---

## 📡 API Reference

### Health Check
```bash
GET /health
```

Response:
```json
{
  "status": "healthy",
  "ffmpeg": true,
  "disk_free_mb": 450
}
```

---

### Trim Video
```bash
POST /trim
X-API-Key: your-secret-key

{
  "video_url": "https://example.com/video.mp4",
  "duration": 5,
  "start": 0
}
```

Response:
```json
{
  "url": "https://pub-xxx.r2.dev/trimmed_abc123.mp4",
  "job_id": "abc123"
}
```

---

### Concatenate Videos
```bash
POST /concat
X-API-Key: your-secret-key

{
  "video_urls": [
    "https://example.com/video1.mp4",
    "https://example.com/video2.mp4",
    "https://example.com/video3.mp4"
  ],
  "trim_duration": 5
}
```

Response:
```json
{
  "url": "https://pub-xxx.r2.dev/concat_def456.mp4",
  "job_id": "def456"
}
```

---

### Merge Audio
```bash
POST /merge-audio
X-API-Key: your-secret-key

{
  "video_url": "https://example.com/video.mp4",
  "audio_url": "https://example.com/audio.mp3",
  "shortest": true
}
```

---

### Add Subtitles
```bash
POST /add-subtitles
X-API-Key: your-secret-key

{
  "video_url": "https://example.com/video.mp4",
  "subtitles": [
    {"text": "Species Name", "start": 0, "end": 5, "position": "bottom"},
    {"text": "Cambrian Period", "start": 0, "end": 5, "position": "top"}
  ],
  "font_size": 24,
  "font_color": "white"
}
```

⚠️ **Warning**: This endpoint requires video re-encoding and may be slow/timeout on free tier for long videos.

---

### Full Evolution Pipeline
```bash
POST /process-evolution
X-API-Key: your-secret-key

{
  "video_urls": [
    "https://api.example.com/video1.mp4",
    "https://api.example.com/video2.mp4"
  ],
  "audio_url": "https://example.com/background.mp3",
  "species_data": [
    {"name": "Pikaia", "period": "Cambrian", "mya": 500},
    {"name": "Tiktaalik", "period": "Devonian", "mya": 375}
  ],
  "trim_duration": 5,
  "add_text": false
}
```

Response:
```json
{
  "url": "https://pub-xxx.r2.dev/evolution_ghi789.mp4",
  "job_id": "ghi789",
  "videos_processed": 2,
  "audio_added": true,
  "text_added": false
}
```

---

## ⚡ Koyeb Free Tier Limits

| Resource | Limit | Impact |
|----------|-------|--------|
| **RAM** | 256 MB | Can't process large videos |
| **CPU** | 0.1 vCPU | Slow re-encoding |
| **Storage** | 1 GB | Limited temp space |
| **Bandwidth** | 100 GB/month | Plenty for API |
| **Sleep** | After 5 min inactivity | Cold starts (~10s) |

### What Works Well ✅
- Trimming (stream copy)
- Concatenating (stream copy)
- Audio merging
- Videos under 50MB each
- Up to 10 videos per concat

### What May Struggle ⚠️
- Subtitle burning (re-encoding)
- Videos over 100MB
- More than 15 videos at once
- HD re-encoding

### Recommendations
1. **Skip subtitle encoding** - Add text in your video generation prompt instead
2. **Use stream copy** - `-c copy` operations are fast and low-memory
3. **Limit video count** - Keep to 10 or fewer videos per concat
4. **Use R2** - Faster than returning files directly

---

## 🔧 n8n Integration

### HTTP Request Node Configuration

```json
{
  "method": "POST",
  "url": "https://ffmpeg-api-YOUR_ID.koyeb.app/concat",
  "headers": {
    "Content-Type": "application/json",
    "X-API-Key": "your-secret-key"
  },
  "body": {
    "video_urls": ["{{ $json.video1 }}", "{{ $json.video2 }}"],
    "trim_duration": 5
  }
}
```

### Example n8n Workflow Nodes

#### 1. Concat Videos Node
```json
{
  "parameters": {
    "method": "POST",
    "url": "https://YOUR-KOYEB-URL.koyeb.app/concat",
    "sendHeaders": true,
    "headerParameters": {
      "parameters": [
        {"name": "Content-Type", "value": "application/json"},
        {"name": "X-API-Key", "value": "your-api-key"}
      ]
    },
    "sendBody": true,
    "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify({ video_urls: $('Get Videos').all().map(v => v.json.url), trim_duration: 5 }) }}"
  },
  "type": "n8n-nodes-base.httpRequest",
  "name": "Concat Videos via FFmpeg API"
}
```

#### 2. Add Audio Node
```json
{
  "parameters": {
    "method": "POST",
    "url": "https://YOUR-KOYEB-URL.koyeb.app/merge-audio",
    "sendHeaders": true,
    "headerParameters": {
      "parameters": [
        {"name": "Content-Type", "value": "application/json"},
        {"name": "X-API-Key", "value": "your-api-key"}
      ]
    },
    "sendBody": true,
    "specifyBody": "json",
    "jsonBody": "={ \"video_url\": \"{{ $json.url }}\", \"audio_url\": \"https://your-audio-url.mp3\", \"shortest\": true }"
  },
  "type": "n8n-nodes-base.httpRequest",
  "name": "Merge Audio via FFmpeg API"
}
```

---

## 🐛 Troubleshooting

### "Container killed - Out of memory"
- Video too large
- Too many videos
- Solution: Reduce video count or size

### "Request timeout"
- Processing taking too long
- Solution: Use `/concat` with `trim_duration` to limit video length

### "FFmpeg failed"
- Check video URLs are accessible
- Ensure videos have same resolution/codec for concat
- Check Koyeb logs for details

### Cold Start Delays
- First request after inactivity takes ~10s
- Solution: Use a health check ping to keep warm

### Keeping Service Warm
Add this to n8n as a scheduled workflow (every 4 minutes):
```json
{
  "method": "GET",
  "url": "https://YOUR-KOYEB-URL.koyeb.app/health"
}
```

---

## 📊 Comparison: Cloudinary vs FFmpeg API

| Aspect | Cloudinary | FFmpeg on Koyeb |
|--------|------------|-----------------|
| **Cost** | 25 credits/month limit | Unlimited |
| **Speed** | Faster (CDN) | Slower (processing) |
| **Concat** | ✅ Easy | ✅ Works |
| **Trim** | ✅ Easy | ✅ Works |
| **Audio** | ✅ Easy | ✅ Works |
| **Subtitles** | ✅ Easy | ⚠️ Slow |
| **Complexity** | Low (URL transforms) | Medium (API calls) |
| **Reliability** | High | Medium (cold starts) |

### Recommendation
- **For < 8 videos/month**: Use Cloudinary (simpler)
- **For unlimited videos**: Use FFmpeg on Koyeb (this guide)
- **Hybrid**: Use FFmpeg for processing, R2 for storage

---

## ✅ Deployment Checklist

- [ ] GitHub repository created
- [ ] Files added (app.py, Dockerfile, requirements.txt)
- [ ] Koyeb account created
- [ ] Service deployed
- [ ] Environment variables set
- [ ] API key configured
- [ ] (Optional) R2 bucket created
- [ ] (Optional) R2 credentials added
- [ ] Health check verified
- [ ] Test API call successful

---

## 🎬 Complete Example: Evolution Video

```bash
curl -X POST https://YOUR-KOYEB-URL.koyeb.app/process-evolution \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "video_urls": [
      "https://your-api.com/video1.mp4",
      "https://your-api.com/video2.mp4",
      "https://your-api.com/video3.mp4"
    ],
    "audio_url": "https://your-storage.com/background.mp3",
    "species_data": [
      {"name": "Pikaia", "period": "Cambrian", "mya": 500},
      {"name": "Haikouichthys", "period": "Cambrian", "mya": 530},
      {"name": "Tiktaalik", "period": "Devonian", "mya": 375}
    ],
    "trim_duration": 5,
    "add_text": false
  }'
```

Response:
```json
{
  "url": "https://pub-xxx.r2.dev/evolution_abc123.mp4",
  "job_id": "abc123",
  "videos_processed": 3,
  "audio_added": true,
  "text_added": false
}
```

---

## 🆘 Support

- **Koyeb Docs**: https://www.koyeb.com/docs
- **FFmpeg Docs**: https://ffmpeg.org/documentation.html
- **R2 Docs**: https://developers.cloudflare.com/r2/

---

**Happy video processing! 🎥**
