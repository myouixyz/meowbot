
# Spotify Integration Setup

To enable Spotify support in your Discord bot, follow these steps:

## 1. Create a Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Log in with your Spotify account
3. Click "Create an App"
4. Fill in the details:
   - App name: "Discord Music Bot"
   - App description: "Music bot for Discord"
5. Click "Create"

## 2. Get Your Credentials

1. In your new app, you'll see:
   - **Client ID** - Copy this value
   - **Client Secret** - Click "Show Client Secret" and copy this value

## 3. Add to Replit Secrets

1. In your Replit project, open the "Secrets" tab (lock icon in sidebar)
2. Add these two secrets:
   - Key: `SPOTIFY_CLIENT_ID`, Value: `your_client_id_here`
   - Key: `SPOTIFY_CLIENT_SECRET`, Value: `your_client_secret_here`

## 4. Restart Your Bot

After adding the secrets, restart your bot. It will now support:

- Spotify track URLs
- Spotify playlist URLs  
- Spotify album URLs
- Automatic conversion to YouTube for playback

## Supported Commands

- `meow play https://open.spotify.com/track/...` - Play a Spotify track
- `meow play https://open.spotify.com/playlist/...` - Add Spotify playlist to queue
- `meow play song name` - Search and play from YouTube
- `meow queue` - View current queue
- `meow nowplaying` - Show current track
- `meow loop track/queue/off` - Set loop mode
- `meow volume 50` - Set volume (0-100)
- `meow shuffle` - Shuffle queue
- `meow skip` - Skip current track

The bot will automatically search YouTube for Spotify tracks since Discord bots cannot directly stream from Spotify.
