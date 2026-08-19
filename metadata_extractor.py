# metadata_extractor.py - Extracts ALL required metadata

import cv2
import json
import os
from datetime import datetime
from pathlib import Path
import yt_dlp
import subprocess

class MetadataExtractor:
    def __init__(self):
        pass
    
    def extract_full_metadata(self, video_path, quality_results, video_url=None):
        """
        Extract ALL metadata for a video
        """
        metadata = {}
        
        # === 1. Basic video info ===
        cap = cv2.VideoCapture(str(video_path))
        
        metadata["filename"] = os.path.basename(video_path)
        metadata["file_size_mb"] = os.path.getsize(video_path) / (1024 * 1024)
        
        # Video properties
        metadata["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        metadata["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        metadata["resolution"] = f"{metadata['width']}x{metadata['height']}"
        metadata["fps"] = cap.get(cv2.CAP_PROP_FPS)
        metadata["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        metadata["duration"] = metadata["frame_count"] / metadata["fps"] if metadata["fps"] > 0 else 0
        
        # Codec info (using ffprobe if available)
        metadata["codec"] = self.get_codec_info(video_path)
        
        cap.release()
        
        # === 2. From quality results ===
        if quality_results:
            metadata["blur_score"] = quality_results.get("blur_score", 0)
            metadata["compression_score"] = quality_results.get("compression_score", 0)
            metadata["quality_score"] = quality_results.get("quality_score", 0)
            metadata["face_count"] = quality_results.get("face_count", 0)
            metadata["average_face_size"] = quality_results.get("average_face_size", 0)
            metadata["has_heavy_occlusion"] = quality_results.get("has_heavy_occlusion", False)
            
            # Hashes
            metadata["sha256_hash"] = quality_results.get("sha256_hash", None)
            metadata["perceptual_hash"] = quality_results.get("perceptual_hash", None)
        
        # === 3. Platform metadata ===
        if video_url:
            platform_meta = self.extract_platform_metadata(video_url)
            metadata.update(platform_meta)
        
        # === 4. Download metadata ===
        metadata["download_timestamp"] = datetime.now().isoformat()
        metadata["download_date"] = datetime.now().strftime("%Y-%m-%d")
        
        # === 5. Label (to be set externally) ===
        metadata["label"] = None  # Will be set by collector
        
        return metadata
    
    def get_codec_info(self, video_path):
        """Extract codec information using ffprobe"""
        try:
            cmd = [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout.strip() or "unknown"
        except:
            return "unknown"
    
    def extract_platform_metadata(self, url):
        """Extract metadata from platform URL using yt-dlp"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                return {
                    "platform": info.get('extractor', 'unknown'),
                    "original_url": url,
                    "video_id": info.get('id', 'unknown'),
                    "upload_date": info.get('upload_date', None),
                    "title": info.get('title', 'unknown'),
                    "uploader": info.get('uploader', 'unknown'),
                    "view_count": info.get('view_count', 0),
                    "like_count": info.get('like_count', 0),
                    "comment_count": info.get('comment_count', 0),
                    "description": info.get('description', '')[:500]  # Truncate
                }
        except Exception as e:
            return {
                "platform": "unknown",
                "original_url": url,
                "error_extracting_metadata": str(e)
            }