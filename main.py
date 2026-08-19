# main.py - COMPLETE WORKING VERSION WITH ALL METHODS

import os
import sys
import json
import random
import time
import logging
from pathlib import Path
from datetime import datetime
import schedule
import yt_dlp

# Import modules
from config import CONFIG
from search_queries import REAL_CATEGORIES, FAKE_CATEGORIES
from quality_checker import QualityChecker
from metadata_extractor import MetadataExtractor
from drive_uploader import DriveUploader

# Setup logging
import codecs
if sys.stdout.encoding != 'utf-8':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/collection.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class DeepfakeCollector:
    def __init__(self):
        self.config = CONFIG
        self.quality_checker = QualityChecker(CONFIG)
        self.metadata_extractor = MetadataExtractor()
        self.drive_uploader = DriveUploader(CONFIG)
        
        # Create directories
        for path in CONFIG["PATHS"].values():
            Path(path).mkdir(parents=True, exist_ok=True)
        
        # Load progress
        self.progress_file = Path("logs/progress.json")
        self.progress = self.load_progress()
        
        # Initialize counters
        self.real_count = len(self.progress.get("real", []))
        self.fake_count = len(self.progress.get("fake", []))
        
        logger.info(">>> Starting Deepfake Collector")
        logger.info(f"Current: {self.real_count} real, {self.fake_count} fake")
    
    def load_progress(self):
        """Load collection progress"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
            except:
                return {"real": [], "fake": [], "processed": []}
        return {"real": [], "fake": [], "processed": []}
    
    def save_progress(self):
        """Save collection progress"""
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)
    
    def search_youtube_videos(self, query, max_count):
        """Search YouTube videos"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'ignoreerrors': True,
        }
        
        # Ensure query has person/face keywords
        if "person" not in query.lower() and "face" not in query.lower():
            query = f"{query} person face"
        
        search_query = f"ytsearch{max_count * 3}:{query}"
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Searching YouTube for: {query}")
                info = ydl.extract_info(search_query, download=False)
                
                if not info or 'entries' not in info:
                    return []
                
                filtered_videos = []
                for entry in info['entries']:
                    if not entry:
                        continue
                    
                    duration = entry.get('duration', 0)
                    if 3 <= duration <= 120:
                        video_id = entry.get('id')
                        filtered_videos.append({
                            'url': f"https://youtube.com/watch?v={video_id}",
                            'id': video_id,
                            'duration': duration,
                            'title': entry.get('title', 'Unknown'),
                            'uploader': entry.get('uploader', 'Unknown'),
                            'platform': 'youtube'
                        })
                        logger.info(f"   ✅ ACCEPT: {entry.get('title', 'Unknown')[:40]}... ({duration}s)")
                    else:
                        if duration:
                            logger.info(f"   SKIP: {entry.get('title', 'Unknown')[:40]}... ({duration}s)")
                
                filtered_videos = filtered_videos[:max_count]
                logger.info(f"Found {len(filtered_videos)} YouTube videos")
                return filtered_videos
                
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            return []
    
    def search_tiktok_videos(self, query, max_count):
        """Search TikTok videos"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'ignoreerrors': True,
            'cookiefile': 'cookies/tiktok_cookies.txt' if os.path.exists('cookies/tiktok_cookies.txt') else None,
        }
        
        # Ensure query has person/face keywords
        if "person" not in query.lower() and "face" not in query.lower():
            query = f"{query} person face"
        
        search_query = f"tiktoksearch{max_count * 3}:{query}"
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Searching TikTok for: {query}")
                info = ydl.extract_info(search_query, download=False)
                
                if not info or 'entries' not in info:
                    return []
                
                filtered_videos = []
                for entry in info['entries']:
                    if not entry:
                        continue
                    
                    duration = entry.get('duration', 0)
                    if 3 <= duration <= 120:
                        filtered_videos.append({
                            'url': entry.get('webpage_url'),
                            'id': entry.get('id'),
                            'duration': duration,
                            'title': entry.get('title', 'Unknown'),
                            'uploader': entry.get('uploader', 'Unknown'),
                            'platform': 'tiktok'
                        })
                        logger.info(f"   ✅ ACCEPT: {entry.get('title', 'Unknown')[:40]}... ({duration}s)")
                    else:
                        if duration:
                            logger.info(f"   SKIP: {entry.get('title', 'Unknown')[:40]}... ({duration}s)")
                
                filtered_videos = filtered_videos[:max_count]
                logger.info(f"Found {len(filtered_videos)} TikTok videos")
                return filtered_videos
                
        except Exception as e:
            logger.error(f"TikTok search error: {e}")
            return []
    
    def search_and_filter_videos(self, query, platform, max_count):
        """Search for videos and filter by duration"""
        if platform == "youtube":
            return self.search_youtube_videos(query, max_count)
        elif platform == "tiktok":
            return self.search_tiktok_videos(query, max_count)
        else:
            logger.warning(f"Platform {platform} not supported")
            return []
    
    def download_filtered_videos(self, video_urls, platform):
        """Download only the filtered videos"""
        if not video_urls:
            return False
        
        ydl_opts = {
            'outtmpl': os.path.join(CONFIG["PATHS"]["download"], f'{platform}_%(id)s.%(ext)s'),
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': True,
            'ignoreerrors': True,
            'sleep_interval': random.randint(3, 8),
            'user_agent': random.choice([
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            ]),
        }
        
        # Add cookies if available
        cookie_file = Path(CONFIG["PATHS"]["cookies"]) / f"{platform}_cookies.txt"
        if cookie_file.exists():
            ydl_opts['cookiefile'] = str(cookie_file)
            logger.info(f"Using cookies for {platform}")
        
        downloaded = 0
        for video in video_urls:
            url = video['url']
            try:
                logger.info(f"Downloading: {video['title'][:50]}... ({video['duration']}s)")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    downloaded += 1
                    logger.info(f"  ✅ Downloaded: {video['id']}")
            except Exception as e:
                logger.error(f"  ❌ Failed to download {url}: {e}")
        
        return downloaded > 0
    
    def process_category(self, category_name, category_type):
        """Process one category"""
        # Check if we've reached target
        target = CONFIG["TARGET_REAL"] if category_type == "real" else CONFIG["TARGET_FAKE"]
        current_count = len(self.progress.get(category_type, []))
        
        if current_count >= target:
            logger.info(f"Target reached for {category_type}: {current_count}/{target}")
            return
        
        # Get category data
        if category_type == "real":
            cat_data = REAL_CATEGORIES.get(category_name)
        else:
            cat_data = FAKE_CATEGORIES.get(category_name)
        
        if not cat_data:
            logger.warning(f"Unknown category: {category_name}")
            return
        
        # Use YouTube (most reliable)
        platform = "youtube"
        query = random.choice(cat_data["queries"])
        
        # Add hashtag sometimes
        if random.random() > 0.5:
            hashtag = random.choice(cat_data.get("hashtags", [""]))
            if hashtag:
                query += f" {hashtag}"
        
        logger.info(f"Searching: '{query}' on {platform} ({category_type}/{category_name})")
        
        # Search for videos
        filtered_videos = self.search_and_filter_videos(query, platform, CONFIG["BATCH_SIZE"])
        
        if not filtered_videos:
            logger.warning(f"No videos found for {category_name}")
            return
        
        # Download videos
        downloaded = self.download_filtered_videos(filtered_videos, platform)
        
        if not downloaded:
            logger.warning(f"Failed to download videos for {category_name}")
            return
        
        # Process each downloaded video
        accepted_count = 0
        download_path = Path(CONFIG["PATHS"]["download"])
        video_files = list(download_path.glob("*.mp4"))
        
        logger.info(f"📁 Found {len(video_files)} video files in downloads folder")
        
        for video_path in video_files:
            try:
                logger.info(f"\n📹 Processing: {video_path.name}")
                
                # Run quality checks
                passed, quality_results, reason = self.quality_checker.check_all_criteria(str(video_path))
                
                if not passed:
                    logger.info(f"❌ REJECTED: {reason}")
                    try:
                        os.remove(video_path)
                    except:
                        pass
                    continue
                
                # Extract metadata
                metadata = self.metadata_extractor.extract_full_metadata(
                    str(video_path), 
                    quality_results
                )
                
                # Add category and label
                metadata["category"] = category_name
                metadata["label"] = category_type
                metadata["category_type"] = category_type
                
                # Upload to Drive
                logger.info("📤 Uploading to Google Drive...")
                uploaded = self.drive_uploader.upload_video(str(video_path), metadata)
                
                if uploaded:
                    accepted_count += 1
                    
                    # Update progress
                    video_id = metadata.get("sha256_hash", video_path.stem)
                    if video_id not in self.progress.get(category_type, []):
                        self.progress[category_type].append(video_id)
                    
                    self.progress["processed"].append({
                        "video_id": video_id,
                        "category": category_name,
                        "type": category_type,
                        "timestamp": datetime.now().isoformat(),
                    })
                    
                    self.save_progress()
                    
                    # Update counters
                    if category_type == "real":
                        self.real_count += 1
                    else:
                        self.fake_count += 1
                    
                    logger.info(f"✅ UPLOADED {category_name}: {video_id[:8]}...")
                else:
                    logger.warning(f"❌ Failed to upload {video_path.name}")
                
                # Remove local file
                try:
                    os.remove(video_path)
                    logger.info(f"🗑️ Deleted local: {video_path.name}")
                except:
                    pass
                
            except Exception as e:
                logger.error(f"❌ Error processing {video_path}: {e}")
                try:
                    os.remove(video_path)
                except:
                    pass
        
        logger.info(f"\n📊 {category_type}/{category_name}: {accepted_count} accepted")
        logger.info(f"📈 Total: {self.real_count} real, {self.fake_count} fake")
    
    def run_batch(self):
        """Run one complete batch"""
        logger.info(f"\n{'='*60}")
        logger.info(f"RUNNING BATCH - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")
        
        # Check if targets reached
        if self.real_count >= CONFIG["TARGET_REAL"] and self.fake_count >= CONFIG["TARGET_FAKE"]:
            logger.info("ALL TARGETS REACHED! Stopping.")
            return False
        
        # Select categories
        real_categories = list(REAL_CATEGORIES.keys())
        fake_categories = list(FAKE_CATEGORIES.keys())
        
        # Shuffle for variety
        random.shuffle(real_categories)
        random.shuffle(fake_categories)
        
        # Process 1 real category
        if real_categories and self.real_count < CONFIG["TARGET_REAL"]:
            self.process_category(real_categories[0], "real")
        
        # Pause between real and fake
        time.sleep(random.randint(30, 60))
        
        # Process 1 fake category
        if fake_categories and self.fake_count < CONFIG["TARGET_FAKE"]:
            self.process_category(fake_categories[0], "fake")
        
        # Log summary
        logger.info(f"\n📊 BATCH COMPLETE: {self.real_count} real, {self.fake_count} fake")
        logger.info(f"Progress: {self.real_count/CONFIG['TARGET_REAL']*100:.1f}% real, {self.fake_count/CONFIG['TARGET_FAKE']*100:.1f}% fake")
        
        return True

# ============ MAIN ============
if __name__ == "__main__":
    try:
        collector = DeepfakeCollector()
        
        # Run once immediately
        collector.run_batch()
        
        # Schedule daily at 2 AM, 10 AM, and 6 PM
        schedule.every().day.at("02:00").do(collector.run_batch)
        schedule.every().day.at("10:00").do(collector.run_batch)
        schedule.every().day.at("18:00").do(collector.run_batch)
        
        logger.info("\n⏰ Scheduled for 2 AM, 10 AM, and 6 PM daily")
        logger.info("Press Ctrl+C to stop\n")
        
        while True:
            schedule.run_pending()
            time.sleep(60)
            
            # Check if targets reached
            if collector.real_count >= CONFIG["TARGET_REAL"] and collector.fake_count >= CONFIG["TARGET_FAKE"]:
                logger.info("\n🎯 ALL TARGETS REACHED! Auto-stopping.")
                break
                
    except KeyboardInterrupt:
        logger.info("\n🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()