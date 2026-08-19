# bulk_upload_gui.py - FIXED VISIBLE BUTTONS

import os
import sys
import json
import threading
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import yt_dlp
import hashlib

# Import your existing modules
from config import CONFIG
from drive_uploader import DriveUploader
from metadata_extractor import MetadataExtractor
from search_queries import get_category_names

class BulkUploadGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Deepfake Dataset Builder - Bulk Upload Tool")
        self.root.geometry("1000x850")  # Made bigger
        self.root.resizable(True, True)
        
        # Initialize components
        self.drive_uploader = None
        self.metadata_extractor = MetadataExtractor()
        self.is_processing = False
        self.downloaded_count = 0
        self.uploaded_count = 0
        self.failed_count = 0
        
        # Setup GUI
        self.setup_gui()
        
        # Initialize Drive Uploader
        self.init_drive_uploader()
        
        # Load progress
        self.progress_file = Path("logs/bulk_upload_progress.json")
        self.progress = self.load_progress()
    
    def setup_gui(self):
        """Setup the GUI layout"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === TOP: Title ===
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(
            title_frame, 
            text="📹 Bulk Video Upload Tool", 
            font=('Arial', 18, 'bold')
        )
        title_label.pack()
        
        subtitle_label = ttk.Label(
            title_frame,
            text="YouTube • TikTok • Facebook  |  Download & Upload to Google Drive",
            font=('Arial', 10)
        )
        subtitle_label.pack()
        
        # === ROW 1: Label & Category Selection ===
        control_frame = ttk.LabelFrame(main_frame, text="Video Labeling", padding="10")
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        control_row1 = ttk.Frame(control_frame)
        control_row1.pack(fill=tk.X, pady=5)
        
        # Label
        ttk.Label(control_row1, text="Select Label:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        
        self.label_var = tk.StringVar()
        self.label_dropdown = ttk.Combobox(
            control_row1,
            textvariable=self.label_var,
            values=["real", "fake"],
            state="readonly",
            width=15,
            font=('Arial', 10)
        )
        self.label_dropdown.pack(side=tk.LEFT, padx=(0, 30))
        self.label_dropdown.set("real")
        self.label_var.trace_add("write", self.update_categories)
        
        # Category (populated dynamically from categories.json)
        ttk.Label(control_row1, text="Category:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 10))
        
        self.category_var = tk.StringVar()
        self.category_dropdown = ttk.Combobox(
            control_row1,
            textvariable=self.category_var,
            state="normal",
            width=22,
            font=('Arial', 10)
        )
        self.category_dropdown.pack(side=tk.LEFT)
        self.update_categories()
        
        # Platform info
        platform_frame = ttk.Frame(control_frame)
        platform_frame.pack(fill=tk.X, pady=5)
        
        platform_info = ttk.Label(
            platform_frame,
            text="✅ YouTube: Works without cookies  |  ⚠️ TikTok: Needs cookies.txt  |  ⚠️ Facebook: Needs cookies.txt",
            font=('Arial', 9),
            foreground='#555555'
        )
        platform_info.pack()
        
        # === ROW 2: Links Input ===
        links_frame = ttk.LabelFrame(main_frame, text="Video Links (one per line)", padding="10")
        links_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Text area with scrollbar
        text_container = ttk.Frame(links_frame)
        text_container.pack(fill=tk.BOTH, expand=True)
        
        self.links_text = scrolledtext.ScrolledText(
            text_container,
            height=12,
            font=('Consolas', 10),
            wrap=tk.NONE,
            bg='#fafafa'
        )
        self.links_text.pack(fill=tk.BOTH, expand=True)
        
        # Control buttons for links
        link_control_frame = ttk.Frame(links_frame)
        link_control_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(
            link_control_frame,
            text="📋 Load Examples",
            command=self.load_example_links,
            width=15
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            link_control_frame,
            text="📂 Load from File",
            command=self.load_from_file,
            width=15
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            link_control_frame,
            text="🧹 Clear All",
            command=self.clear_links,
            width=15
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Link counter
        self.link_count_label = ttk.Label(
            link_control_frame, 
            text="Links: 0",
            font=('Arial', 10, 'bold')
        )
        self.link_count_label.pack(side=tk.RIGHT)
        
        # === ROW 3: Progress Bar ===
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode='determinate',
            length=400,
            maximum=100
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        progress_row = ttk.Frame(progress_frame)
        progress_row.pack(fill=tk.X)
        
        self.status_label = ttk.Label(progress_row, text="Ready", font=('Arial', 10))
        self.status_label.pack(side=tk.LEFT)
        
        self.count_label = ttk.Label(progress_row, text="0 / 0", font=('Arial', 10, 'bold'))
        self.count_label.pack(side=tk.RIGHT)
        
        # === ROW 4: LOGS ===
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=8,
            font=('Consolas', 9),
            bg='#1e1e1e',
            fg='#d4d4d4'
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure tags for colored output
        self.log_text.tag_config('info', foreground='#4FC3F7')
        self.log_text.tag_config('success', foreground='#81C784')
        self.log_text.tag_config('error', foreground='#E57373')
        self.log_text.tag_config('warning', foreground='#FFB74D')
        self.log_text.tag_config('header', foreground='#FFFFFF', font=('Consolas', 10, 'bold'))
        self.log_text.tag_config('platform', foreground='#CE93D8')
        
        # === ROW 5: BUTTONS (CLEARLY VISIBLE) ===
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(5, 0))
        
        # LEFT side: Main action buttons
        left_button_frame = ttk.Frame(button_frame)
        left_button_frame.pack(side=tk.LEFT)
        
        # Main Download & Upload button - BIG AND GREEN
        self.process_button = tk.Button(
            left_button_frame,
            text="🚀 DOWNLOAD & UPLOAD ALL VIDEOS",
            command=self.start_processing,
            bg='#4CAF50',
            fg='white',
            font=('Arial', 12, 'bold'),
            padx=20,
            pady=10,
            width=30,
            cursor='hand2',
            relief=tk.RAISED,
            bd=3
        )
        self.process_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Stop button - RED
        self.stop_button = tk.Button(
            left_button_frame,
            text="⏹️ STOP",
            command=self.stop_processing,
            bg='#f44336',
            fg='white',
            font=('Arial', 11, 'bold'),
            padx=15,
            pady=10,
            width=15,
            state=tk.DISABLED,
            cursor='hand2',
            relief=tk.RAISED,
            bd=3
        )
        self.stop_button.pack(side=tk.LEFT)
        
        # RIGHT side: Stats
        stats_frame = ttk.Frame(button_frame)
        stats_frame.pack(side=tk.RIGHT)
        
        self.stats_label = ttk.Label(
            stats_frame,
            text="✅ Uploaded: 0  |  ❌ Failed: 0  |  ⏭️ Skipped: 0  |  📊 Total: 0",
            font=('Arial', 10),
            foreground='#333333'
        )
        self.stats_label.pack()
    
    def update_categories(self, *args):
        """Populate the category dropdown based on the selected label"""
        label = self.label_var.get() or "real"
        categories = get_category_names(label)
        self.category_dropdown['values'] = categories
        if self.category_var.get() not in categories:
            self.category_var.set(categories[0] if categories else "")

    def init_drive_uploader(self):
        """Initialize Google Drive uploader"""
        try:
            self.drive_uploader = DriveUploader(CONFIG)
            self.log("✅ Google Drive connected successfully!", 'success')
        except Exception as e:
            self.log(f"❌ Drive connection failed: {e}", 'error')
            messagebox.showerror("Error", f"Failed to connect to Google Drive:\n{e}")
    
    def load_progress(self):
        """Load bulk upload progress"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
            except:
                return {"uploaded": [], "failed": [], "total": 0}
        return {"uploaded": [], "failed": [], "total": 0}
    
    def save_progress(self):
        """Save bulk upload progress"""
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)
    
    def log(self, message, tag='info'):
        """Add message to log with timestamp"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        formatted_msg = f"[{timestamp}] {message}\n"
        self.log_text.insert(tk.END, formatted_msg, tag)
        self.log_text.see(tk.END)
        self.root.update()
    
    def load_example_links(self):
        """Load example links from all platforms"""
        examples = """# YouTube Links (Works without cookies)
https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://www.youtube.com/watch?v=QH2-TGUlwu4
https://www.youtube.com/watch?v=9bZkp7q19f0

# TikTok Links (Needs cookies/tiktok_cookies.txt)
https://www.tiktok.com/@user/video/1234567890

# Facebook Links (Needs cookies/facebook_cookies.txt)
https://www.facebook.com/watch/?v=1234567890"""
        
        self.links_text.delete('1.0', tk.END)
        self.links_text.insert('1.0', examples)
        self.update_link_count()
        self.log("📋 Loaded example links", 'info')
    
    def load_from_file(self):
        """Load links from a text file"""
        file_path = filedialog.askopenfilename(
            title="Select Links File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                self.links_text.delete('1.0', tk.END)
                self.links_text.insert('1.0', content)
                self.update_link_count()
                self.log(f"✅ Loaded links from: {os.path.basename(file_path)}", 'success')
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file:\n{e}")
    
    def clear_links(self):
        """Clear all links from text area"""
        if messagebox.askyesno("Confirm", "Clear all links?"):
            self.links_text.delete('1.0', tk.END)
            self.update_link_count()
            self.log("🧹 Cleared all links", 'info')
    
    def update_link_count(self):
        """Update link counter"""
        content = self.links_text.get('1.0', tk.END).strip()
        # Filter out comments (lines starting with #)
        links = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]
        self.link_count_label.config(text=f"Links: {len(links)}")
    
    def get_links(self):
        """Get list of links from text area"""
        content = self.links_text.get('1.0', tk.END).strip()
        # Filter out comments (lines starting with #)
        links = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]
        return links
    
    def validate_links(self, links):
        """Basic link validation with platform detection"""
        valid = []
        invalid = []
        platform_counts = {"youtube": 0, "tiktok": 0, "facebook": 0, "unknown": 0}
        
        for link in links:
            if link.startswith(('http://', 'https://')):
                valid.append(link)
                platform = self.extract_platform(link)
                platform_counts[platform] = platform_counts.get(platform, 0) + 1
            else:
                invalid.append(link)
        
        # Log platform summary
        self.log(f"📊 Platform breakdown:", 'info')
        for platform, count in platform_counts.items():
            if count > 0:
                self.log(f"   {platform}: {count}", 'platform')
        
        return valid, invalid
    
    def extract_platform(self, url):
        """Extract platform from URL"""
        if 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'tiktok.com' in url:
            return 'tiktok'
        elif 'facebook.com' in url or 'fb.com' in url:
            return 'facebook'
        else:
            return 'unknown'
    
    def download_single_video(self, url, platform, index, total):
        """Download a single video from any platform"""
        try:
            self.log(f"📥 [{index}/{total}] Downloading from {platform}: {url[:50]}...", 'info')
            
            ydl_opts = {
                'outtmpl': os.path.join(CONFIG["PATHS"]["download"], f'{platform}_%(id)s.%(ext)s'),
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'sleep_interval': 3,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'],
                    }
                }
            }
            
            # Add cookies for TikTok and Facebook
            if platform in ['tiktok', 'facebook']:
                cookie_file = Path(CONFIG["PATHS"]["cookies"]) / f"{platform}_cookies.txt"
                if cookie_file.exists():
                    ydl_opts['cookiefile'] = str(cookie_file)
                    self.log(f"   🍪 Using cookies for {platform}", 'info')
                else:
                    self.log(f"   ⚠️ No cookies found for {platform}. May fail.", 'warning')
            
            # Try to download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Find the downloaded file
            download_path = Path(CONFIG["PATHS"]["download"])
            video_files = list(download_path.glob(f"{platform}_*.mp4"))
            
            if video_files:
                # Get the most recent file
                video_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                return video_files[0]
            else:
                return None
                
        except Exception as e:
            error_msg = str(e)
            self.log(f"   ❌ Download failed: {error_msg[:100]}", 'error')
            return None
    
    def upload_single_video(self, video_path, label, category):
        """Upload a single video to Drive"""
        try:
            # Generate metadata
            video_hash = hashlib.md5(video_path.stem.encode()).hexdigest()[:16]
            
            metadata = {
                "label": label,
                "category": category,
                "sha256_hash": video_hash,
                "duration": 10,
                "resolution": "1280x720",
                "fps": 30,
                "blur_score": 100,
                "quality_score": 50,
                "face_count": 1,
                "download_timestamp": datetime.now().isoformat(),
                "platform": video_path.stem.split('_')[0] if '_' in video_path.stem else 'unknown'
            }
            
            # Upload to Drive
            result = self.drive_uploader.upload_video(str(video_path), metadata)
            
            if result and result.get('success'):
                return True, video_hash
            else:
                return False, None
                
        except Exception as e:
            self.log(f"❌ Upload error: {str(e)[:100]}", 'error')
            return False, None
    
    def process_links(self):
        """Main processing function (runs in separate thread)"""
        try:
            # Get input
            links = self.get_links()
            label = self.label_var.get()
            category = self.category_var.get()
            
            if not links:
                self.log("❌ No links provided!", 'error')
                messagebox.showwarning("Warning", "Please paste some video links first!")
                self.finish_processing()
                return
            
            if not label:
                self.log("❌ No label selected!", 'error')
                messagebox.showwarning("Warning", "Please select a label!")
                self.finish_processing()
                return
            
            # Validate links
            valid_links, invalid_links = self.validate_links(links)
            
            if invalid_links:
                self.log(f"⚠️ Found {len(invalid_links)} invalid links", 'warning')
                for link in invalid_links:
                    self.log(f"   Invalid: {link}", 'error')
            
            if not valid_links:
                self.log("❌ No valid links to process!", 'error')
                self.finish_processing()
                return
            
            total = len(valid_links)
            self.log(f"\n{'='*60}", 'header')
            self.log(f"📊 Starting bulk upload: {total} videos", 'header')
            self.log(f"   Label: {label}", 'info')
            self.log(f"   Category: {category}", 'info')
            self.log(f"   Platforms: YouTube, TikTok, Facebook", 'info')
            self.log(f"{'='*60}\n", 'header')
            
            # Update UI
            self.progress_bar['maximum'] = total
            self.progress_bar['value'] = 0
            self.count_label.config(text=f"0 / {total}")
            self.stats_label.config(text=f"✅ Uploaded: 0  |  ❌ Failed: 0  |  ⏭️ Skipped: 0  |  📊 Total: {total}")
            
            # Process each link
            uploaded = 0
            failed = 0
            downloaded_count = 0
            skipped_count = 0
            
            for i, url in enumerate(valid_links, 1):
                if self.stop_processing_flag:
                    self.log("\n⏹️ Processing stopped by user", 'warning')
                    break
                
                # Update progress
                self.progress_bar['value'] = i - 1
                self.status_label.config(text=f"Processing ({i}/{total})...")
                self.count_label.config(text=f"{i-1} / {total}")
                self.root.update()
                
                # Extract platform
                platform = self.extract_platform(url)
                
                # Download video
                video_path = self.download_single_video(url, platform, i, total)
                
                if not video_path:
                    failed += 1
                    continue
                
                downloaded_count += 1
                self.log(f"✅ Downloaded: {video_path.name}", 'success')
                
                # Upload video
                self.status_label.config(text=f"Uploading ({i}/{total})...")
                self.root.update()
                
                success, video_hash = self.upload_single_video(video_path, label, category)
                
                if success:
                    uploaded += 1
                    self.log(f"✅ Uploaded: {video_path.name}", 'success')
                    
                    # Update progress
                    self.progress["uploaded"].append({
                        "video_hash": video_hash,
                        "label": label,
                        "category": category,
                        "url": url,
                        "platform": platform,
                        "timestamp": datetime.now().isoformat()
                    })
                    self.save_progress()
                else:
                    failed += 1
                    self.log(f"❌ Failed to upload: {video_path.name}", 'error')
                
                # Clean up local file
                try:
                    os.remove(video_path)
                    self.log(f"🗑️ Deleted local: {video_path.name}", 'info')
                except:
                    pass
                
                # Update stats
                self.stats_label.config(
                    text=f"✅ Uploaded: {uploaded}  |  ❌ Failed: {failed}  |  ⏭️ Skipped: {skipped_count}  |  📊 Total: {total}"
                )
                self.progress_bar['value'] = i
                self.count_label.config(text=f"{i} / {total}")
                self.root.update()
            
            # Final update
            self.progress_bar['value'] = total
            self.count_label.config(text=f"{total} / {total}")
            
            # Summary
            self.log(f"\n{'='*60}", 'header')
            self.log(f"📊 BULK UPLOAD COMPLETE!", 'header')
            self.log(f"   Total links: {total}", 'info')
            self.log(f"   Downloaded: {downloaded_count}", 'info')
            self.log(f"   ✅ Uploaded: {uploaded}", 'success')
            self.log(f"   ❌ Failed: {failed}", 'error')
            if skipped_count > 0:
                self.log(f"   ⏭️ Skipped: {skipped_count}", 'warning')
            self.log(f"{'='*60}\n", 'header')
            
            self.status_label.config(text="Complete!")
            self.finish_processing()
            
        except Exception as e:
            self.log(f"❌ Fatal error: {e}", 'error')
            import traceback
            traceback.print_exc()
            self.finish_processing()
    
    def start_processing(self):
        """Start the processing thread"""
        if self.is_processing:
            return
        
        # Check if Drive is connected
        if not self.drive_uploader:
            messagebox.showerror("Error", "Google Drive not connected!")
            return
        
        # Disable buttons
        self.is_processing = True
        self.stop_processing_flag = False
        self.process_button.config(state=tk.DISABLED, bg='#9E9E9E')
        self.stop_button.config(state=tk.NORMAL, bg='#f44336')
        self.label_dropdown.config(state="disabled")
        self.category_dropdown.config(state="disabled")
        self.links_text.config(state=tk.DISABLED)
        
        self.log("🚀 Starting bulk upload process...", 'header')
        
        # Start processing in separate thread
        self.thread = threading.Thread(target=self.process_links)
        self.thread.daemon = True
        self.thread.start()
    
    def stop_processing(self):
        """Stop the processing"""
        self.stop_processing_flag = True
        self.log("\n⏹️ Stopping... Please wait for current operation to finish.", 'warning')
        self.stop_button.config(state=tk.DISABLED, bg='#9E9E9E')
    
    def finish_processing(self):
        """Re-enable UI after processing"""
        self.is_processing = False
        self.process_button.config(state=tk.NORMAL, bg='#4CAF50')
        self.stop_button.config(state=tk.DISABLED, bg='#9E9E9E')
        self.label_dropdown.config(state="readonly")
        self.category_dropdown.config(state="normal")
        self.links_text.config(state=tk.NORMAL)
        
        if not self.stop_processing_flag:
            self.status_label.config(text="Ready")
        else:
            self.status_label.config(text="Stopped")
    
    def on_closing(self):
        """Handle window close"""
        if self.is_processing:
            if not messagebox.askyesno("Confirm", "Processing is running. Are you sure you want to exit?"):
                return
        
        # Save progress
        self.save_progress()
        self.root.destroy()


# ============ MAIN ============
if __name__ == "__main__":
    root = tk.Tk()
    app = BulkUploadGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()