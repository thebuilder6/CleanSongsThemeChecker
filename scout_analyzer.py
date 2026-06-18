import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
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
st.write("Evaluate Spotify playlists for teen appropriateness and download/clone clean reports.")

# ==========================================
# 1. SECRETS LOADING (Completely hidden from UI)
# ==========================================
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
# If running locally, default redirect is localhost:8501 (Streamlit's local address)
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI', 'http://127.0.0.1:8501')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Safely attempt to override with Streamlit Cloud Secrets (if they exist)
try:
    if 'SPOTIPY_CLIENT_ID' in st.secrets:
        SPOTIPY_CLIENT_ID = st.secrets['SPOTIPY_CLIENT_ID']
    if 'SPOTIPY_CLIENT_SECRET' in st.secrets:
        SPOTIPY_CLIENT_SECRET = st.secrets['SPOTIPY_CLIENT_SECRET']
    if 'SPOTIPY_REDIRECT_URI' in st.secrets:
        SPOTIPY_REDIRECT_URI = st.secrets['SPOTIPY_REDIRECT_URI']
    if 'GEMINI_API_KEY' in st.secrets:
        GEMINI_API_KEY = st.secrets['GEMINI_API_KEY']
except Exception:
    pass

# ==========================================
# 2. SIDEBAR CONFIGURATION (User settings only)
# ==========================================
with st.sidebar:
    st.header("⚙️ Settings")
    enable_search = st.checkbox("Enable Google Search Grounding", value=False)
    
    # Show a log out option to reset authorization if needed
    if st.button("🔌 Disconnect Spotify"):
        if 'token_info' in st.session_state:
            del st.session_state.token_info
        if os.path.exists(".spotifycache"):
            os.remove(".spotifycache")
        st.rerun()

# ==========================================
# 3. SPOTIFY OAUTH SETUP & URL REDIRECT CATCHER
# ==========================================
if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET or not GEMINI_API_KEY:
    st.error("⚠️ App Configuration Error: The required API keys are missing. Please verify your .env file or Streamlit Secrets are set up correctly.")
    st.stop()

# Set up the authorization manager
sp_oauth = SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope='playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative',
    cache_path=".spotifycache",
    show_dialog=True
)

# Read the URL query parameters to check if Spotify redirected us back with a code
url_code = st.query_params.get("code")

if "token_info" not in st.session_state:
    if url_code:
        try:
            # Exchange the redirect code for an access token
            token_info = sp_oauth.get_access_token(url_code, as_dict=True)
            st.session_state.token_info = token_info
            # Clear the browser address bar query code to keep it clean
            st.query_params.clear()
        except Exception as e:
            st.error(f"Failed to authenticate with Spotify: {e}")
    else:
        # Check if we have a valid cached token locally
        cached_token = sp_oauth.get_cached_token()
        if cached_token:
            st.session_state.token_info = cached_token

# ==========================================
# 4. LOGIN SCREEN (If not authenticated)
# ==========================================
if "token_info" not in st.session_state:
    st.write("### 🔑 Connect Your Spotify Account")
    st.write("Spotify strictly requires secure verification to view and manage playlists.")
    
    # Generate the Spotify login link
    auth_url = sp_oauth.get_authorize_url()
    st.link_button("🔗 Connect to Spotify", auth_url, type="primary", use_container_width=True)
    st.stop() # Freeze the app here until she logs in

# If authenticated, load Spotify client
sp = spotipy.Spotify(auth=st.session_state.token_info['access_token'])
gem_client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 5. HELPER FUNCTIONS
# ==========================================
def get_playlist_details(playlist_url, sp_client):
    try:
        playlist_id = playlist_url.split('/')[-1].split('?')[0]
        playlist_info = sp_client.playlist(playlist_id)
        playlist_name = playlist_info.get('name', 'My Scout Playlist')
        
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
                track_uri = track.get('uri')
                song_list.append((track_name, artist_name, track_uri))
        return playlist_name, song_list
    except Exception as e:
        st.error(f"Failed to load Spotify playlist. Is the link correct? Error: {e}")
        return None, []

def analyze_songs_in_batches(song_batch, gemini_client):
    song_list_text = "\n".join([f"{i+1}. {track} by {artist}" for i, (track, artist, _) in enumerate(song_batch)])
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

# Initialize session state variables
if 'safe_songs' not in st.session_state:
    st.session_state.safe_songs = []
if 'borderline_songs' not in st.session_state:
    st.session_state.borderline_songs = []
if 'inappropriate_songs' not in st.session_state:
    st.session_state.inappropriate_songs = []
if 'playlist_name' not in st.session_state:
    st.session_state.playlist_name = ""
if 'analyzed' not in st.session_state:
    st.session_state.analyzed = False

# ==========================================
# 6. APP CONTENT (Visible only when logged in)
# ==========================================
playlist_link = st.text_input(
    "Enter Spotify Playlist Link:", 
    placeholder="https://open.spotify.com/playlist/..."
)

if st.button("🚀 Start Song Safety Check", use_container_width=True):
    if not playlist_link:
        st.warning("⚠️ Please paste a Spotify playlist link first.")
    else:
        # 1. Fetch Songs & Details
        with st.spinner("Fetching songs from Spotify..."):
            playlist_name, songs = get_playlist_details(playlist_link, sp)
            st.session_state.playlist_name = playlist_name
            
        if songs:
            st.success(f"Loaded '{playlist_name}' ({len(songs)} songs)! Starting analysis...")
            
            # Reset session state lists
            st.session_state.safe_songs = []
            st.session_state.borderline_songs = []
            st.session_state.inappropriate_songs = []
            
            # Create placeholders for visual progress
            progress_bar = st.progress(0.0)
            status_text = st.empty()
            log_container = st.container()
            
            batch_size = 10
            total_songs = len(songs)
            
            # 2. Process Batches
            for i in range(0, total_songs, batch_size):
                batch = songs[i:i+batch_size]
                current_batch_num = (i // batch_size) + 1
                total_batches = (total_songs + batch_size - 1) // batch_size
                
                status_text.text(f"Analyzing batch {current_batch_num} of {total_batches}...")
                
                batch_result = analyze_songs_in_batches(batch, gem_client)
                
                # Split the text by the "---" separator
                song_blocks = batch_result.split('---')
                for block in song_blocks:
                    block = block.strip()
                    if not block:
                        continue
                        
                    # Extract song data elements safely
                    song_name = "Unknown Song"
                    rating = None
                    reason = "No explanation available."
                    track_uri = None
                    
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
                    
                    # Associate the Spotify URI
                    for s_name, s_artist, s_uri in batch:
                        if s_name.lower() in song_name.lower():
                            track_uri = s_uri
                            break
                    
                    song_data = {"name": song_name, "reason": reason, "uri": track_uri, "raw_block": block}
                    
                    # Sort song and show on screen immediately
                    if rating == 1:
                        st.session_state.safe_songs.append(song_data)
                        with log_container:
                            st.write(f"✅ **{song_name}** is Safe.")
                    elif rating == 2:
                        st.session_state.borderline_songs.append(song_data)
                        with log_container:
                            st.warning(f"⚠️ **{song_name}** is Borderline.")
                    elif rating == 3:
                        st.session_state.inappropriate_songs.append(song_data)
                        with log_container:
                            st.error(f"🚨 **{song_name}** is Inappropriate.")
                    else:
                        if "RATING: 1" in block:
                            st.session_state.safe_songs.append(song_data)
                            with log_container:
                                st.write(f"✅ **{song_name}** is Safe.")
                        else:
                            st.session_state.borderline_songs.append(song_data)
                            with log_container:
                                st.warning(f"❓ **{song_name}** flagged for Review.")
                
                # Update progress bar
                progress_percent = min((i + batch_size) / total_songs, 1.0)
                progress_bar.progress(progress_percent)
                
                # Wait to prevent rate limits
                time.sleep(5)
                
            status_text.text("Analysis Complete!")
            st.session_state.analyzed = True

# ==========================================
# 7. RENDER RESULTS & CLONE ACTION
# ==========================================
if st.session_state.analyzed:
    st.write("---")
    st.header("📊 Final Review Report")
    
    col1, col2, col3 = st.columns(3)
    col1.metric(label="✅ Safe Songs", value=len(st.session_state.safe_songs))
    col2.metric(label="⚠️ Borderline", value=len(st.session_state.borderline_songs))
    col3.metric(label="🚨 Inappropriate", value=len(st.session_state.inappropriate_songs))
    
    # CLONE PLAYLIST COMPONENT
    if st.session_state.safe_songs:
        st.subheader("🪄 Make a Clean Duplicate Playlist")
        st.write("Click this button to automatically create a brand new, pre-cleaned duplicate of this playlist on your Spotify account.")
        
        if st.button("➕ Create Clean Copy on Spotify", use_container_width=True, type="primary"):
            with st.spinner("Creating your clean playlist..."):
                try:
                    user_id = sp.current_user()['id']
                    clean_name = f"{st.session_state.playlist_name} (Clean Version)"
                    
                    new_playlist = sp.user_playlist_create(
                        user=user_id,
                        name=clean_name,
                        public=False,
                        description="Automatically generated clean version of the playlist for scouting events."
                    )
                    
                    new_playlist_id = new_playlist['id']
                    safe_uris = [song['uri'] for song in st.session_state.safe_songs if song['uri'] is not None]
                    
                    for k in range(0, len(safe_uris), 100):
                        sp.playlist_add_items(new_playlist_id, safe_uris[k:k+100])
                        
                    st.success(f"🎉 **Success!** Created **'{clean_name}'** on your Spotify account with {len(safe_uris)} safe songs!")
                except Exception as e:
                    st.error(f"Could not create playlist on Spotify: {e}")
                    
    # Folder tabs to easily separate and evaluate songs
    tab1, tab2 = st.tabs(["⚠️ Borderline (Requires Decisions)", "🚨 Inappropriate (Suggested Removals)"])
    
    with tab1:
        if st.session_state.borderline_songs:
            st.write("Review these songs and click below to read details:")
            for idx, song in enumerate(st.session_state.borderline_songs):
                with st.expander(f"🔍 {idx+1}. {song['name']}"):
                    st.markdown(f"**Assigned Rating:** 2-Borderline")
                    st.info(f"**Why it was flagged:** {song['reason']}")
        else:
            st.success("No borderline songs found in this playlist!")
            
    with tab2:
        if st.session_state.inappropriate_songs:
            st.write("These songs are recommended for removal. Click to see details:")
            for idx, song in enumerate(st.session_state.inappropriate_songs):
                with st.expander(f"❌ {idx+1}. {song['name']}"):
                    st.markdown(f"**Assigned Rating:** 3-Inappropriate")
                    st.error(f"**Why it was flagged:** {song['reason']}")
        else:
            st.success("No inappropriate songs found in this playlist!")
            if not st.session_state.borderline_songs:
                st.balloons()
    
    # Printable report
    st.write("---")
    with st.expander("📝 Show Comprehensive Flagged Songs Report (Printable/Copyable Text)"):
        st.subheader("Leader Evaluation Report")
        
        report_text = f"SCOUT MUSIC PLAYLIST REPORT\n"
        report_text += f"Playlist: {st.session_state.playlist_name}\n"
        report_text += f"Playlist URL: {playlist_link}\n"
        report_text += f"="*40 + "\n\n"
        
        if st.session_state.borderline_songs:
            report_text += f"⚠️ BORDERLINE SONGS (Requires Manual Review) - Total: {len(st.session_state.borderline_songs)}\n"
            report_text += f"-"*40 + "\n"
            for idx, song in enumerate(st.session_state.borderline_songs, 1):
                report_text += f"{idx}. {song['name']}\n"
                report_text += f"   - Reasoning: {song['reason']}\n\n"
        else:
            report_text += "✅ No borderline songs identified.\n\n"
            
        report_text += "\n"
        
        if st.session_state.inappropriate_songs:
            report_text += f"🚨 INAPPROPRIATE SONGS (Suggested Removals) - Total: {len(st.session_state.inappropriate_songs)}\n"
            report_text += f"-"*40 + "\n"
            for idx, song in enumerate(st.session_state.inappropriate_songs, 1):
                report_text += f"{idx}. {song['name']}\n"
                report_text += f"   - Reasoning: {song['reason']}\n\n"
        else:
            report_text += "✅ No inappropriate songs identified.\n\n"
        
        st.code(report_text, language="text")
        
        st.download_button(
            label="📥 Download Detailed Report (.txt file)",
            data=report_text,
            file_name="scout_playlist_evaluation.txt",
            mime="text/plain",
            use_container_width=True
        )