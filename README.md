# AI API - Image & Video Generation

A free, async API for AI image and video generation with 22 models including Midjourney, Flux, Sora, Veo3, and more.

**Base URL:** `https://vivid-inez-rudraksh-d0d461d8.koyeb.app`

---

## Authentication

All protected endpoints require an API key via header:

```bash
-H "X-API-Key: YOUR_API_KEY"
```

Or using Bearer token:
```bash
-H "Authorization: Bearer YOUR_API_KEY"
```

---

## Quick Start

```bash
# 1. Create a task
curl -X POST https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"prompt": "a dragon", "model": "nanobanana"}'
# Returns: {"task_id": "abc123def456", "status": "pending"}

# 2. Wait for processing (typically 30-180 seconds)
sleep 60

# 3. Get result (ONE-TIME RETRIEVAL - task auto-deletes after fetch)
curl https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/tasks/abc123def456 \
  -H "X-API-Key: YOUR_KEY"
# Returns: {"status": "completed", "data": [{"url": "https://..."}]}
```

---

## Endpoints

### Public Endpoints (No Auth Required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check with active task stats |
| GET | `/v1/models` | List all available models |

### Protected Endpoints (Auth Required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/images/generations` | Create image generation task |
| POST | `/v1/images/edits` | Create image editing task |
| POST | `/v1/videos/generations` | Create video generation task |
| POST | `/v1/videos/image-to-video` | Create image-to-video task |
| GET | `/v1/tasks/{task_id}` | Get task status and result |

---

## Task Lifecycle

```
pending → processing → completed (auto-deletes after retrieval)
                    ↘ failed (auto-deletes after retrieval)
```

### ⚠️ Important: One-Time Retrieval

**Tasks auto-delete after first successful fetch.** This means:
- You can only retrieve the result **once**
- Store the result immediately when you fetch it
- If you need the result again, you must create a new task
- Failed tasks also auto-delete after retrieval

### Task Response (Pending/Processing)

```json
{
  "task_id": "abc123def456",
  "status": "pending",
  "type": "image",
  "created_at": 1703694000
}
```

### Task Response (Completed)

```json
{
  "task_id": "abc123def456",
  "status": "completed",
  "type": "image",
  "created_at": 1703694000,
  "created": 1703694045,
  "data": [
    {
      "url": "https://tempfile.aiquickdraw.com/...",
      "revised_prompt": "a majestic dragon..."
    }
  ]
}
```

### Task Response (Failed)

```json
{
  "task_id": "abc123def456",
  "status": "failed",
  "type": "image",
  "created_at": 1703694000,
  "error": {
    "message": "Image generation timed out"
  }
}
```

---

## Image Generation

### POST `/v1/images/generations`

Create an image from a text prompt.

#### Request

```bash
curl -X POST https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{
    "prompt": "a majestic lion in the savanna at sunset",
    "model": "nanobanana",
    "aspect_ratio": "16:9"
  }'
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | **required** | Text description of the image |
| `model` | string | `nanobanana` | Model to use (see Image Models) |
| `aspect_ratio` | string | `1:1` | Aspect ratio: `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `2:3`, `3:2` |
| `resolution` | string | `1k` | Resolution: `1K`, `2K`, `4K` (model dependent) |
| `quality` | string | `basic` | Quality: `basic`, `standard`, `hd` |
| `output_format` | string | `png` | Format: `png`, `jpg`, `webp` |
| `version` | string | `7` | Midjourney version: `5`, `6`, `7` |
| `speed` | string | `fast` | Midjourney speed: `fast`, `turbo`, `relax` |

---

## Image Models

### nanobanana (Fastest)
```json
{
  "prompt": "a cute cat",
  "model": "nanobanana",
  "aspect_ratio": "1:1",
  "output_format": "png"
}
```

### nanobanana-pro (High Quality)
```json
{
  "prompt": "detailed portrait",
  "model": "nanobanana-pro",
  "aspect_ratio": "1:1",
  "resolution": "2K"
}
```

### flux-kontext-pro
```json
{
  "prompt": "artistic landscape",
  "model": "flux-kontext-pro",
  "aspect_ratio": "16:9"
}
```

### flux-kontext-max
```json
{
  "prompt": "ultra detailed scene",
  "model": "flux-kontext-max",
  "aspect_ratio": "1:1"
}
```

### flux2-flex
```json
{
  "prompt": "creative artwork",
  "model": "flux2-flex",
  "aspect_ratio": "1:1",
  "resolution": "1K"
}
```

### flux2-pro (Supports Editing)
```json
{
  "prompt": "professional photo",
  "model": "flux2-pro",
  "aspect_ratio": "1:1",
  "resolution": "2K"
}
```

### midjourney
```json
{
  "prompt": "fantasy illustration --v 7",
  "model": "midjourney",
  "aspect_ratio": "1:1",
  "version": "7",
  "speed": "fast"
}
```

### seedream4
```json
{
  "prompt": "dreamy scene",
  "model": "seedream4",
  "aspect_ratio": "1:1",
  "resolution": "1K"
}
```

### seedream4.5
```json
{
  "prompt": "artistic creation",
  "model": "seedream4.5",
  "aspect_ratio": "1:1",
  "quality": "standard"
}
```

---

## Image Editing

### POST `/v1/images/edits`

Edit an existing image with a prompt.

```bash
curl -X POST https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/images/edits \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{
    "prompt": "add sunglasses to the person",
    "model": "nanobanana-pro",
    "image_url": "https://example.com/photo.jpg",
    "aspect_ratio": "1:1",
    "resolution": "1K"
  }'
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | **required** | Edit instructions |
| `image_url` | string | **required** | URL of image to edit |
| `image_urls` | array | - | Multiple image URLs |
| `model` | string | `nanobanana-pro` | Model: `nanobanana-pro`, `flux2-pro`, `midjourney` |
| `aspect_ratio` | string | `1:1` | Output aspect ratio |
| `resolution` | string | `1K` | Output resolution |

---

## Video Generation

### POST `/v1/videos/generations`

Create a video from a text prompt.

```bash
curl -X POST https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/videos/generations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{
    "prompt": "a spaceship flying through nebula clouds",
    "model": "kling-v2-6",
    "duration": 10,
    "aspect_ratio": "16:9"
  }'
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | **required** | Text description |
| `model` | string | `kling-v2-6` | Video model (see below) |
| `duration` | int | `10` | Duration in seconds (5-30) |
| `aspect_ratio` | string | `16:9` | Aspect ratio |
| `resolution` | string | `720p` | Resolution: `480p`, `720p`, `1080p` |
| `quality` | string | `540p` | Quality setting |

---

## Video Models

### veo3 / veo3_fast (Google Veo 3)
```json
{
  "prompt": "cinematic drone shot of mountains",
  "model": "veo3",
  "aspect_ratio": "16:9"
}
```

### sora2 / sora_video2_pro (OpenAI Sora)
```json
{
  "prompt": "a cat playing piano",
  "model": "sora2",
  "aspect_ratio": "9:16"
}
```

### kling-v2-6 (Kling AI)
```json
{
  "prompt": "ocean waves at sunset",
  "model": "kling-v2-6",
  "duration": 10,
  "aspect_ratio": "9:16"
}
```

### wan/2-5 (Wan AI with Sound)
```json
{
  "prompt": "fireworks celebration",
  "model": "wan/2-5",
  "duration": 10,
  "aspect_ratio": "9:16",
  "resolution": "720p"
}
```

### grok-imagine-normal / fun / spicy
```json
{
  "prompt": "funny dancing robot",
  "model": "grok-imagine-fun",
  "aspect_ratio": "2:3"
}
```

### pixverse (Requires Image)
```json
{
  "prompt": "animate this character",
  "model": "pixverse",
  "duration": 5,
  "quality": "540p"
}
```

---

## Image to Video

### POST `/v1/videos/image-to-video`

Animate an image into a video.

```bash
curl -X POST https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/videos/image-to-video \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{
    "prompt": "the character starts walking forward",
    "image_url": "https://example.com/character.png",
    "model": "kling-v2-6",
    "duration": 5
  }'
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | **required** | Motion description |
| `image_url` | string | **required** | Source image URL |
| `model` | string | `kling-v2-6` | Video model |
| `duration` | int | `10` | Duration in seconds |
| `aspect_ratio` | string | - | Override aspect ratio |

### Models Supporting Image-to-Video
- `kling-v2-6`
- `seedance_v1_pro`
- `hailuo2.3-pro`
- `hailuo2.3-standard`
- `pixverse`

---

## Example: Complete Workflow

```bash
# 1. Create task
TASK_ID=$(curl -s -X POST https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"prompt":"a magical forest","model":"nanobanana"}' | jq -r '.task_id')

echo "Task created: $TASK_ID"

# 2. Wait for processing (adjust time based on model)
echo "Waiting for processing..."
sleep 60

# 3. Fetch result (ONE-TIME ONLY - saves immediately)
RESULT=$(curl -s https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/tasks/$TASK_ID \
  -H "X-API-Key: YOUR_KEY")

STATUS=$(echo $RESULT | jq -r '.status')

if [ "$STATUS" = "completed" ]; then
  URL=$(echo $RESULT | jq -r '.data[0].url')
  echo "✅ Done! Image: $URL"
  
  # Save result immediately (task is now deleted from server)
  echo $RESULT > result_$TASK_ID.json
  
elif [ "$STATUS" = "processing" ]; then
  echo "⏳ Still processing, wait longer and try again"
  
elif [ "$STATUS" = "failed" ]; then
  ERROR=$(echo $RESULT | jq -r '.error.message')
  echo "❌ Failed: $ERROR"
fi
```

### Polling Strategy (Recommended)

```bash
# Create task
TASK_ID=$(curl -s -X POST https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"prompt":"a dragon","model":"nanobanana"}' | jq -r '.task_id')

# Poll with exponential backoff
WAIT_TIME=30
MAX_ATTEMPTS=10
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
  echo "Checking status (attempt $((ATTEMPT+1))/$MAX_ATTEMPTS)..."
  
  RESULT=$(curl -s https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/tasks/$TASK_ID \
    -H "X-API-Key: YOUR_KEY")
  
  STATUS=$(echo $RESULT | jq -r '.status')
  
  if [ "$STATUS" = "completed" ]; then
    URL=$(echo $RESULT | jq -r '.data[0].url')
    echo "✅ Success! $URL"
    break
  elif [ "$STATUS" = "failed" ]; then
    echo "❌ Failed: $(echo $RESULT | jq -r '.error.message')"
    break
  elif [ "$STATUS" = "processing" ] || [ "$STATUS" = "pending" ]; then
    echo "⏳ Still processing, waiting ${WAIT_TIME}s..."
    sleep $WAIT_TIME
    WAIT_TIME=$((WAIT_TIME + 15))  # Increase wait time
    ATTEMPT=$((ATTEMPT + 1))
  else
    echo "❌ Task not found (may have been retrieved already)"
    break
  fi
done
```

---

## Processing Times

Typical processing times by model type:

| Model Type | Typical Time |
|------------|--------------|
| Image (nanobanana) | 30-60 seconds |
| Image (flux, midjourney) | 60-120 seconds |
| Video (text-to-video) | 3-5 minutes |
| Video (image-to-video) | 2-4 minutes |

**Recommendation:** Wait at least 60 seconds for images, 3 minutes for videos before first check.

---

## All Models Reference

### Image Models (9)

| Model | Speed | Quality | Supports Editing |
|-------|-------|---------|------------------|
| `nanobanana` | ⚡ Fast | Good | ❌ |
| `nanobanana-pro` | Medium | High | ✅ |
| `flux-kontext-pro` | Medium | High | ❌ |
| `flux-kontext-max` | Slow | Very High | ❌ |
| `flux2-flex` | Medium | High | ❌ |
| `flux2-pro` | Slow | Very High | ✅ |
| `midjourney` | Medium | Very High | ✅ |
| `seedream4` | Medium | High | ❌ |
| `seedream4.5` | Medium | High | ❌ |

### Video Models (13)

| Model | Type | Duration | Notes |
|-------|------|----------|-------|
| `veo3` | Text | - | Google Veo 3 |
| `veo3_fast` | Text | - | Google Veo 3 Fast |
| `sora2` / `sora_video2_pro` | Text | - | OpenAI Sora 2 |
| `kling-v2-6` | Text/Image | 5-30s | Sound enabled |
| `wan/2-5` | Text | 5-30s | Sound enabled |
| `grok-imagine-normal` | Text | - | Normal mode |
| `grok-imagine-fun` | Text | - | Fun mode |
| `grok-imagine-spicy` | Text | - | Spicy mode |
| `seedance_v1_pro` | Image | 5-30s | Image required |
| `hailuo2.3-pro` | Image | 5-30s | Image required |
| `hailuo2.3-standard` | Image | 5-30s | Image required |
| `pixverse` | Image | 5-30s | Image required |

---

## Error Handling

### Error Response

```json
{
  "error": {
    "message": "Invalid or missing API key"
  }
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success - Task retrieved |
| 400 | Bad request (missing params) |
| 401 | Unauthorized (invalid API key) |
| 404 | Task not found (may have been retrieved already) |
| 500 | Server error |

---

## Best Practices

### 1. Store Results Immediately
Since tasks auto-delete after retrieval, save the response immediately:

```bash
curl https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/tasks/$TASK_ID \
  -H "X-API-Key: YOUR_KEY" \
  -o result.json
```

### 2. Use Appropriate Wait Times
Don't poll too frequently. Recommended intervals:
- Images: Check after 60s, then every 30s
- Videos: Check after 180s, then every 60s

### 3. Handle 404 Errors
A 404 means the task was already retrieved or never existed:

```python
response = requests.get(f"{BASE_URL}/v1/tasks/{task_id}", headers=headers)
if response.status_code == 404:
    print("Task not found - may have been retrieved already")
```

### 4. Implement Retry Logic
If status is still "processing", wait and try again:

```python
import time
import requests

BASE_URL = "https://vivid-inez-rudraksh-d0d461d8.koyeb.app"
headers = {"X-API-Key": "YOUR_KEY"}

def wait_for_task(task_id, max_attempts=10):
    for attempt in range(max_attempts):
        response = requests.get(f"{BASE_URL}/v1/tasks/{task_id}", headers=headers)
        
        if response.status_code == 404:
            return None  # Already retrieved
            
        data = response.json()
        
        if data['status'] == 'completed':
            return data['data'][0]['url']
        elif data['status'] == 'failed':
            raise Exception(data['error']['message'])
        
        time.sleep(30 + (attempt * 15))  # Exponential backoff
    
    raise TimeoutError("Task did not complete in time")
```

---

## Rate Limits

- Max 20 concurrent tasks
- Tasks persist until first retrieval
- No request rate limit

---

## Telegram Bot - Remote API Key Management

Manage your API keys remotely via Telegram bot! Perfect for creating and managing keys on the go.

### Bot Features

- ✅ Create API keys for users
- ✅ Delete API keys by username or specific key
- ✅ List all active API keys
- ✅ Download server error logs
- ✅ Clear error logs
- ✅ Admin-only access (secure)

### Available Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/gen <username>` | Create new API key | `/gen alice` |
| `/del <username>` | Delete all keys for user | `/del alice` |
| `/createkey <username>` | Create key (alternative) | `/createkey bob` |
| `/deletekey <key>` | Delete specific key | `/deletekey zero-alice-abc123` |
| `/listkeys` | List all API keys | `/listkeys` |
| `/geterror` | Download error logs | `/geterror` |
| `/clearerror` | Clear error logs | `/clearerror` |
| `/help` | Show all commands | `/help` |

### Quick Start

1. **Find the bot on Telegram** (contact admin for bot username)
2. **Send a command:**
   ```
   /gen john
   ```
3. **Get your API key:**
   ```
   ✅ Key created:
   zero-john-abc123xyz
   ```
4. **Use the key in your API requests:**
   ```bash
   curl -H "X-API-Key: zero-john-abc123xyz" \
     https://vivid-inez-rudraksh-d0d461d8.koyeb.app/v1/models
   ```

### Example Workflow

```
You: /gen alice
Bot: ✅ Key created: zero-alice-xyz789abc

You: /listkeys
Bot: 📋 API Keys:
     zero-alice-xyz789abc
     zero-bob-def456uvw

You: /del alice
Bot: ✅ Deleted 1 key(s) for user: alice
```

### Security

- Only authorized admin users can use the bot
- All commands require admin verification
- Keys are stored securely in `api_keys.json`
- Unauthorized users receive: `⛔ Unauthorized. Admin access required.`

For detailed bot setup and configuration, see [TELEGRAM_BOT_GUIDE.md](TELEGRAM_BOT_GUIDE.md)

---

## License

MIT

