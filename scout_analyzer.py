import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from google import genai
from google.genai import types
import time
import os
from dotenv import load_dotenv

# Load local environment variables if they exist
load_dotenv()

# Set up the visual look of the website
st.set_page_config(page_title="Scout Playlist Analyzer", page_icon="🎵", layout="centered")

st.title("🎵 Scout Music Theme Analyzer")
st.write("Paste a Spotify playlist link below to automatically check songs for teen appropriateness.")

# ==========================================
# 1. SECRETS LOADING (Completely hidden from UI)
# ==========================================
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# ==========================================
# 2. SIDEBAR CONFIGURATION (User settings only)
# ==========================================
with st.sidebar:
    st.header("⚙️ Settings")
    # Keeping Search disabled by default to save her quota limits
    enable_search = st.checkbox("Enable Google Search Grounding", value=False)

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def get_playlist_tracks(playlist_url, sp_client):
    try:
        playlist_id = playlist_url.split('/')[-1].split('?')[0]
        results = sp_client.playlist_tracks(playlist_id)
        tracks = results['items']
        
        while results['next']:
            results = sp_client.next(results)
            tracks.extend(results['items'])
            
        song_list = []
        for item in tracks:
            track = item.get('item') if 'item' in item else item.get('track')
            if track:
                track_name = track.get('name')
                artists = track.get('artists', [])
                artist_name = artists[0].get('name') if artists else 'Unknown Artist'
                song_list.append((track_name, artist_name))
        return song_list
    except Exception as e:
        st.error(f"Failed to load Spotify playlist. Is the link correct? Error: {e}")
        return []

def analyze_songs_in_batches(song_batch, gemini_client):
    song_list_text = "\n".join([f"{i+1}. {track} by {artist}" for i, (track, artist) in enumerate(song_batch)])
    prompt = f"""
    You are an expert music content reviewer for a public children's scouting event (ages 14-18).
    Evaluate EVERY song in the following list for:
    1. Sexual innuendo or adult situations
    2. Drug or alcohol references
    3. Violence or aggressive themes
    4. General appropriateness for teens

    Format your response EXACTLY like this for EACH song, separating each song's review with "---":
    
    SONG: [Track Name] by [Artist]
    RATING: [Give a rating: 1-Safe, 2-Borderline, 3-Inappropriate]
    REASON: [1-2 short sentences explaining any problematic themes, or why it's safe]
    ---
    
    Songs to evaluate:
    {song_list_text}
    """
    config = None
    if enable_search:
        config = types.GenerateContentConfig(tools=[types.Tool(googleSearch=types.GoogleSearch())])
    
    try:
        response = gemini_client.models.generate_content(
            model='gemini-3.1-flash-lite', 
            contents=prompt, 
            config=config
        )
        return response.text.strip() if response.text else ""
    except Exception as e:
        return f"Error: {e}"

# ==========================================
# 4. USER INTERFACE
# ==========================================
playlist_link = st.text_input(
    "Enter Spotify Playlist Link:", 
    placeholder="https://open.spotify.com/playlist/..."
)

if st.button("🚀 Start Song Safety Check", use_container_width=True):
    # Check if the environment variables are successfully loaded in the background
    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET or not GEMINI_API_KEY:
        st.error("⚠️ App Configuration Error: The required API keys are missing. Please verify your .env file or Streamlit Secrets are set up correctly.")
    elif not playlist_link:
        st.warning("⚠️ Please paste a Spotify playlist link first.")
    else:
        # Initialize clients silently using background environment variables
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET
        ))
        gem_client = genai.Client(api_key=GEMINI_API_KEY)
        
        # 1. Fetch Songs
        with st.spinner("Fetching songs from Spotify..."):
            songs = get_playlist_tracks(playlist_link, sp)
            
        if songs:
            st.success(f"Loaded {len(songs)} songs! Starting analysis...")
            
            # Create placeholders for visual progress
            progress_bar = st.progress(0.0)
            status_text = st.empty()
            log_container = st.container()
            
            # Updated structured lists
            safe_songs = []
            borderline_songs = []
            inappropriate_songs = []
            
            batch_size = 10
            total_songs = len(songs)
            
            # 2. Process Batches
            for i in range(0, total_songs, batch_size):
                batch = songs[i:i+batch_size]
                current_batch_num = (i // batch_size) + 1
                total_batches = (total_songs + batch_size - 1) // batch_size
                
                status_text.text(f"Analyzing batch {current_batch_num} of {total_batches}...")
                
                batch_result = analyze_songs_in_batches(batch, gem_client)
                
                # Split the text by the "---" separator we told Gemini to use
                song_blocks = batch_result.split('---')
                for block in song_blocks:
                    block = block.strip()
                    if not block:
                        continue
                        
                    # Extract song data elements safely
                    song_name = "Unknown Song"
                    rating = None
                    reason = "No explanation available."
                    
                    for line in block.splitlines():
                        line_stripped = line.strip()
                        if line_stripped.upper().startswith("SONG:"):
                            song_name = line_stripped[5:].strip()
                        elif line_stripped.upper().startswith("RATING:"):
                            rating_str = line_stripped[7:].strip()
                            if "1" in rating_str:
                                rating = 1
                            elif "2" in rating_str:
                                rating = 2
                            elif "3" in rating_str:
                                rating = 3
                        elif line_stripped.upper().startswith("REASON:"):
                            reason = line_stripped[7:].strip()
                    
                    song_data = {"name": song_name, "reason": reason, "raw_block": block}
                    
                    # Sort song and show on screen immediately
                    if rating == 1:
                        safe_songs.append(song_data)
                        with log_container:
                            st.write(f"✅ **{song_name}** is Safe.")
                    elif rating == 2:
                        borderline_songs.append(song_data)
                        with log_container:
                            st.warning(f"⚠️ **{song_name}** is Borderline.")
                    elif rating == 3:
                        inappropriate_songs.append(song_data)
                        with log_container:
                            st.error(f"🚨 **{song_name}** is Inappropriate.")
                    else:
                        # Fallback parsing in case model missed format but rating was 1
                        if "RATING: 1" in block:
                            safe_songs.append(song_data)
                            with log_container:
                                st.write(f"✅ **{song_name}** is Safe.")
                        else:
                            borderline_songs.append(song_data)
                            with log_container:
                                st.warning(f"❓ **{song_name}** flagged for Review (unparsed format).")
                
                # Update progress bar
                progress_percent = min((i + batch_size) / total_songs, 1.0)
                progress_bar.progress(progress_percent)
                
                # Wait to prevent rate limits
                time.sleep(5)
                
            status_text.text("Analysis Complete!")
            
            # ==========================================
            # 5. FINAL REPORT PRESENTATION
            # ==========================================
            st.write("---")
            st.header("📊 Final Review Report")
            
            # Displays three colored columns at the top of the report
            col1, col2, col3 = st.columns(3)
            col1.metric(label="✅ Safe Songs", value=len(safe_songs))
            col2.metric(label="⚠️ Borderline", value=len(borderline_songs))
            col3.metric(label="🚨 Inappropriate", value=len(inappropriate_songs))
            
            # Folder tabs to easily separate and evaluate songs
            tab1, tab2 = st.tabs(["⚠️ Borderline (Requires Decisions)", "🚨 Inappropriate (Suggested Removals)"])
            
            with tab1:
                if borderline_songs:
                    st.write("These songs may contain mild themes. **Click on any song below** to review the leader reasons and decide if you want to keep them:")
                    for idx, song in enumerate(borderline_songs):
                        with st.expander(f"🔍 {idx+1}. {song['name']}"):
                            st.markdown(f"**Assigned Rating:** 2-Borderline")
                            st.info(f"**Why it was flagged:** {song['reason']}")
                else:
                    st.success("No borderline songs found in this playlist!")
                    
            with tab2:
                if inappropriate_songs:
                    st.write("These songs are recommended for removal due to strong language or adult themes. **Click on any song** to see details:")
                    for idx, song in enumerate(inappropriate_songs):
                        with st.expander(f"❌ {idx+1}. {song['name']}"):
                            st.markdown(f"**Assigned Rating:** 3-Inappropriate")
                            st.error(f"**Why it was flagged:** {song['reason']}")
                else:
                    st.success("No inappropriate songs found in this playlist!")
                    if not borderline_songs:
                        st.balloons()
            
            # ==========================================
            # 6. COMPREHENSIVE DOWNLOADABLE REPORT
            # ==========================================
            st.write("---")
            with st.expander("📝 Show Comprehensive Flagged Songs Report (Printable/Copyable Text)"):
                st.subheader("Leader Evaluation Report")
                
                report_text = f"SCOUT MUSIC PLAYLIST REPORT\n"
                report_text += f"Playlist URL analyzed: {playlist_link}\n"
                report_text += f"="*40 + "\n\n"
                
                if borderline_songs:
                    report_text += f"⚠️ BORDERLINE SONGS (Requires Manual Review) - Total: {len(borderline_songs)}\n"
                    report_text += f"-"*40 + "\n"
                    for idx, song in enumerate(borderline_songs, 1):
                        report_text += f"{idx}. {song['name']}\n"
                        report_text += f"   - Reasoning: {song['reason']}\n\n"
                else:
                    report_text += "✅ No borderline songs identified.\n\n"
                    
                report_text += "\n"
                
                if inappropriate_songs:
                    report_text += f"🚨 INAPPROPRIATE SONGS (Suggested Removals) - Total: {len(inappropriate_songs)}\n"
                    report_text += f"-"*40 + "\n"
                    for idx, song in enumerate(inappropriate_songs, 1):
                        report_text += f"{idx}. {song['name']}\n"
                        report_text += f"   - Reasoning: {song['reason']}\n\n"
                else:
                    report_text += "✅ No inappropriate songs identified.\n\n"
                
                # Show plain text block for quick copy-pasting
                st.code(report_text, language="text")
                
                # Download button so she can save it instantly as a .txt file
                st.download_button(
                    label="📥 Download Detailed Report (.txt file)",
                    data=report_text,
                    file_name="scout_playlist_evaluation.txt",
                    mime="text/plain",
                    use_container_width=True
                )