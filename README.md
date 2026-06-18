# 🎵 Scout Music Theme Analyzer

A Streamlit-powered tool that screens Spotify playlists for teen-appropriate content — built for Scout leaders, youth event organizers, and anyone curating music for ages 14–18.

## [▶️ Try the Live App](https://cleansongsthemechecker-bm7wnm3tnaslvfyqyn3nz9.streamlit.app/)

## How It Works

1. **Connect your Spotify** — Sign in securely through Spotify OAuth to grant read access to your playlists.
2. **Paste a playlist link** — Drop in any Spotify playlist URL.
3. **AI-powered analysis** — Google Gemini reviews every song in batches, rating each track on a 3-point scale:
   - ✅ **Safe** — Good to go for the event.
   - ⚠️ **Borderline** — Might need a leader's judgment call.
   - 🚨 **Inappropriate** — Flagged for sexual innuendo, drug/alcohol references, violence, or other adult themes.
4. **Review the report** — A dashboard summarizes results with expandable details on why each song was flagged.
5. **One-click clean playlist** — Automatically creates a new "Clean Version" playlist on your Spotify account containing only the safe songs.
6. **Download a printable report** — Export a text report of all borderline and inappropriate songs for leadership review.

## Features

| Feature | Description |
|---|---|
| 🔐 Spotify OAuth | Secure login — no passwords stored |
| 🤖 Gemini AI Screening | Evaluates lyrics & themes across four categories |
| 🔍 Google Search Grounding | Optional toggle for enhanced accuracy via live search |
| 📊 Live Progress Dashboard | Real-time batch progress with per-song status updates |
| 🪄 Auto-Clone Playlist | Creates a cleaned duplicate playlist on your Spotify |
| 📥 Downloadable Report | Export a printable `.txt` evaluation for leaders |

## Tech Stack

- **[Streamlit](https://streamlit.io/)** — Web UI framework
- **[Spotipy](https://spotipy.readthedocs.io/)** — Spotify Web API wrapper
- **[Google Gemini](https://ai.google.dev/)** — AI content analysis (gemini-3.1-flash-lite)
- **Python 3.10+**
