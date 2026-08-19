# drive_uploader.py - ULTIMATE RELIABLE VERSION

import os
import json
import time
import mimetypes
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError

class DriveUploader:
    def __init__(self, config):
        self.config = config
        self.folder_id = config["DRIVE_FOLDER_ID"]
        self.service = None
        self.real_folder_id = None
        self.fake_folder_id = None
        self.metadata_folder_id = None
        
        # Authenticate
        self.authenticate()
        
        # Create subfolders
        print("📁 Setting up Google Drive folders...")
        self.real_folder_id = self.get_or_create_folder("Real_Videos")
        self.fake_folder_id = self.get_or_create_folder("Fake_Videos")
        self.metadata_folder_id = self.get_or_create_folder("Metadata")
        print("✅ Folder setup complete!")
    
    def authenticate(self):
        """Authenticate with Google Drive - RELIABLE VERSION"""
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        creds = None
        token_path = 'credentials/token.json'
        
        # Check if token exists
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                print("✅ Loaded existing credentials")
            except Exception as e:
                print(f"⚠️ Token error: {e}")
                creds = None
        
        # If no valid credentials, login
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    print("✅ Refreshed credentials")
                except Exception as e:
                    print(f"⚠️ Refresh failed: {e}")
                    creds = None
            
            if not creds:
                # Check if credentials.json exists
                if not os.path.exists('credentials/credentials.json'):
                    raise FileNotFoundError(
                        "❌ credentials.json not found!\n"
                        "Please download from Google Cloud Console and place in credentials/ folder"
                    )
                
                print("🔐 Opening browser for authentication...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials/credentials.json', SCOPES
                )
                creds = flow.run_local_server(port=0)
                
                # Save for next time
                os.makedirs('credentials', exist_ok=True)
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
                print("✅ Authentication successful! Token saved.")
        
        self.service = build('drive', 'v3', credentials=creds)
        return self.service
    
    def get_or_create_folder(self, folder_name):
        """Get existing folder or create new one - with retries"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Check if folder already exists
                query = (
                    f"name='{folder_name}' and "
                    f"mimeType='application/vnd.google-apps.folder' and "
                    f"'{self.folder_id}' in parents and "
                    "trashed=false"
                )
                
                results = self.service.files().list(
                    q=query,
                    fields="files(id, name)",
                    pageSize=10
                ).execute()
                
                folders = results.get('files', [])
                
                if folders:
                    folder_id = folders[0]['id']
                    print(f"   📂 Using existing folder: {folder_name}")
                    return folder_id
                
                # Create new folder
                file_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [self.folder_id]
                }
                
                folder = self.service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                
                folder_id = folder.get('id')
                print(f"   📁 Created folder: {folder_name}")
                
                # Wait a moment for folder to be ready
                time.sleep(2)
                return folder_id
                
            except HttpError as error:
                if error.resp.status == 429:  # Rate limit
                    print(f"⚠️ Rate limit, waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    print(f"❌ Error creating folder {folder_name}: {error}")
                    # Fallback: use main folder
                    return self.folder_id
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                return self.folder_id
        
        print(f"⚠️ Failed to create {folder_name}, using main folder")
        return self.folder_id
    
    def upload_video(self, video_path, metadata):
        """
        Upload video to Google Drive - RELIABLE VERSION
        With retries and error handling
        """
        video_hash = metadata.get('sha256_hash', '')[:8]
        if not video_hash:
            video_hash = Path(video_path).stem[:8]
        
        label = metadata.get('label', 'unknown')
        category = metadata.get('category', 'unknown')
        file_name = f"{label}_{category}_{video_hash}.mp4"
        
        # Choose folder
        if label == 'real':
            parent_folder = self.real_folder_id
            folder_type = "Real_Videos"
        elif label == 'fake':
            parent_folder = self.fake_folder_id
            folder_type = "Fake_Videos"
        else:
            parent_folder = self.folder_id
            folder_type = "Root"
        
        print(f"   📤 Uploading to: {folder_type}/{file_name}")
        
        # Check file size
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        print(f"   📏 File size: {file_size_mb:.2f} MB")
        
        # Upload with retries
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                # 1. Upload video
                video_metadata = {
                    'name': file_name,
                    'parents': [parent_folder],
                    'description': json.dumps({
                        'label': label,
                        'category': category,
                        'duration': metadata.get('duration', 0),
                        'resolution': metadata.get('resolution', 'unknown'),
                        'fps': metadata.get('fps', 0),
                        'face_count': metadata.get('face_count', 0),
                        'quality_score': metadata.get('quality_score', 0),
                        'download_date': metadata.get('download_timestamp', ''),
                        'upload_attempt': attempt + 1
                    }, indent=2)
                }
                
                # Use resumable media for large files
                video_media = MediaFileUpload(
                    video_path,
                    mimetype='video/mp4',
                    resumable=True,
                    chunksize=1024 * 1024 * 5  # 5MB chunks
                )
                
                print(f"   ⏳ Uploading video (attempt {attempt + 1}/{max_retries})...")
                
                video_file = self.service.files().create(
                    body=video_metadata,
                    media_body=video_media,
                    fields='id, name, webViewLink'
                ).execute()
                
                video_id = video_file.get('id')
                print(f"   ✅ Video uploaded: {file_name} (ID: {video_id[:8]}...)")
                
                # 2. Upload metadata JSON
                json_metadata = {
                    'video_file_id': video_id,
                    'video_file_name': file_name,
                    'video_url': f"https://drive.google.com/file/d/{video_id}/view",
                    'folder_location': folder_type,
                    'label': label,
                    'category': category,
                    'upload_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                    **metadata
                }
                
                # Remove None values
                json_metadata = {k: v for k, v in json_metadata.items() if v is not None}
                
                # Save temp JSON
                json_path = f"temp_{video_hash}.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(json_metadata, f, indent=2, ensure_ascii=False)
                
                json_name = f"{video_hash}_metadata.json"
                
                json_media = MediaFileUpload(
                    json_path,
                    mimetype='application/json'
                )
                
                json_file = self.service.files().create(
                    body={
                        'name': json_name,
                        'parents': [self.metadata_folder_id],
                        'description': f"Metadata for {file_name}"
                    },
                    media_body=json_media,
                    fields='id, name'
                ).execute()
                
                # Clean up temp file
                try:
                    os.remove(json_path)
                except:
                    pass
                
                print(f"   ✅ Metadata uploaded: {json_name}")
                
                return {
                    'video_id': video_id,
                    'video_name': file_name,
                    'metadata_id': json_file.get('id'),
                    'metadata_name': json_name,
                    'folder': folder_type,
                    'success': True
                }
                
            except HttpError as error:
                if error.resp.status == 429:  # Rate limit
                    print(f"   ⚠️ Rate limit hit, waiting {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                elif error.resp.status == 403:  # Quota exceeded
                    print(f"   ❌ Quota exceeded! Check Google Drive storage.")
                    print(f"   Free storage: 15GB. You have {self.get_folder_size():.2f}GB used.")
                    return None
                else:
                    print(f"   ❌ Google API error: {error}")
                    if attempt < max_retries - 1:
                        print(f"   🔄 Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        continue
                    return None
                    
            except Exception as e:
                print(f"   ❌ Upload error: {e}")
                if attempt < max_retries - 1:
                    print(f"   🔄 Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return None
        
        return None
    
    def get_folder_size(self, folder_id=None):
        """Calculate total size of all files in a folder"""
        try:
            if not folder_id:
                folder_id = self.folder_id
            
            results = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(size)",
                pageSize=1000
            ).execute()
            
            files = results.get('files', [])
            total_size = sum(int(file.get('size', 0)) for file in files)
            
            return total_size / (1024 * 1024 * 1024)  # GB
            
        except Exception as e:
            print(f"⚠️ Error calculating folder size: {e}")
            return 0
    
    def check_storage(self):
        """Check available Google Drive storage"""
        try:
            about = self.service.about().get(fields="storageQuota").execute()
            quota = about.get('storageQuota', {})
            
            used = int(quota.get('usage', 0)) / (1024 * 1024 * 1024)
            total = int(quota.get('limit', 15 * 1024 * 1024 * 1024)) / (1024 * 1024 * 1024)
            
            print(f"📊 Google Drive Storage: {used:.2f}GB / {total:.2f}GB")
            return total - used  # Available space in GB

        except Exception as e:
            print(f"⚠️ Could not check storage: {e}")
            return 15  # Assume 15GB free