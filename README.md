# JelloBait 🟢

An interactive AI-powered chatbot with a living 3D jelly creature — powered by a WebSocket backend, real-time text-to-speech, and a Three.js frontend. Chat with JelloBait and watch it react to your words in real time.

---

## What It Does

JelloBait is a full-stack web application featuring:

- A **3D animated jelly character** rendered in Three.js that reacts visually to the conversation
- A **WebSocket backend** (Python) that handles AI responses, emotion tracking, and audio streaming
- **Real-time text-to-speech** using Microsoft Edge TTS, streamed as MP3 audio to the browser
- An **anger system** — JelloBait gets progressively angrier based on what you say, changing its color, eye shape, and voice
- **Mouth sync** — the character's mouth animates in sync with the AI's voice using Web Audio API frequency analysis

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript, Three.js |
| 3D Model | Blender → exported as GLTF/GLB |
| Environment | HDRI via RGBELoader |
| Audio | Web Audio API (AnalyserNode) |
| Backend | Python, asyncio, websockets |
| AI | Groq API (LLaMA 3.1 8B Instant) via OpenAI SDK |
| TTS | Microsoft Edge TTS (`edge-tts`) |
| Deployment | Railway (WebSocket server) |

---

## Project Structure

```
JELLO.../
├── backend/
│   ├── prompt.txt               # JelloBait's character prompt
│   ├── requirement.txt          # Python dependencies
│   └── voice.py                 # Python WebSocket server & TTS engine
├── frontend/
│   ├── app.js                   # Three.js frontend, WebSocket client, audio engine
│   ├── citrus_orchard_road_...  # HDRI environment map (.hdr)
│   ├── final_jelly_red.glb      # 3D model
│   ├── index.html               # Main HTML page
│   ├── logo.png                 # App icon
│   ├── style.css                # UI styles
│   └── universfield-loud-thu... # Thunder sound effect (.mp3)
├── .env                         # Environment variables (not committed)
└── .gitignore
```

---

## Setup & Installation

### Prerequisites

- Python 3.9+
- Node.js (optional, for local dev server)
- `ffmpeg` installed and accessible on your PATH
- A [Groq API key](https://console.groq.com)

### Backend

```bash
# Install Python dependencies
pip install websockets openai edge-tts pydub python-dotenv numpy

# Create your .env file
echo "GROQ_API_KEY=your_key_here" > .env

# Start the server
python server.py
```

The server runs on `ws://localhost:8765` by default. When deployed to Railway, it reads the `PORT` environment variable automatically.

### Frontend

Serve `index.html` from a local static server (required for ES modules and HDRI loading):

```bash
# Using Python
python -m http.server 5500

# Or using Node.js
npx serve .
```

Then open `http://localhost:5500` in your browser.

---

## How the Anger System Works

JelloBait maintains a hidden anger score (0–100) that changes every response based on user behavior.

| Score | State | Visual |
|---|---|---|
| 0–39 | Chill & Judging | Default teal color |
| 40–59 | Sarcastic & Petty | Default teal color |
| 60–79 | Cold & Humiliating | Turns red |
| 80–99 | Furious & Ruthless | Red + angry eyebrows |
| 100 | GAME OVER | Thunder sound effect |

**Things that raise anger:** typos, bad grammar, spam, insults, weak logic, repetition, breaking immersion.

**Things that lower anger:** genuine apologies, poetic or emotional language.

---

## 3D Model Mesh Names

The GLB model uses these named meshes for animation:

| Mesh Name | Part |
|---|---|
| `Sphere` | Main body |
| `Sphere002` | Black pupils |
| `Sphere003` | Left white eye |
| `Sphere004` | Right white eye |
| `Sphere005` | Mouth |

---

## Environment Variables

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Your Groq API key |
| `PORT` | Server port (default: `8765`, auto-set by Railway) |

---

## Deployment

The backend is designed for [Railway](https://railway.app). Connect your repo, set `GROQ_API_KEY` in the environment variables, and Railway handles the rest. The frontend can be hosted on any static host (Netlify, Vercel, GitHub Pages).

Update the `backendUrl` in `app.js` to point to your deployed Railway WebSocket URL:

```js
const backendUrl = 'wss://your-app.up.railway.app';
```

---

