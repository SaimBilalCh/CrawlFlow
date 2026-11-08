# quality_checker.py - SIMPLIFIED VERSION

import cv2
import numpy as np
import hashlib
import json
from pathlib import Path

class QualityChecker:
    def __init__(self, config):
        self.config = config
        self.acceptance = config["ACCEPTANCE"]
        
        # Use OpenCV's Haar Cascade
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        
        # Load perceptual hash database
        self.perceptual_hashes = set()
        self.load_existing_hashes()
    
    def load_existing_hashes(self):
        """Load previously collected perceptual hashes"""
        hash_file = Path("./metadata/perceptual_hashes.json")
        if hash_file.exists():
            try:
                with open(hash_file, 'r') as f:
                    self.perceptual_hashes = set(json.load(f))
            except:
                self.perceptual_hashes = set()
    
    def check_all_criteria(self, video_path):
        """
        Run ALL acceptance criteria checks - SIMPLIFIED
        """
        results = {}
        reject_reasons = []
        
        # 1. Basic video info
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return False, None, "Cannot open video"
        
        # Get basic metadata
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        results["fps"] = fps
        results["duration"] = duration
        results["resolution"] = f"{width}x{height}"
        results["width"] = width
        results["height"] = height
        results["frame_count"] = frame_count
        
        cap.release()
        
        # Check duration (RELAXED)
        if duration < 3:  # Very permissive
            reject_reasons.append(f"Too short: {duration:.1f}s")
        elif duration > 120:  # Allow up to 2 minutes
            reject_reasons.append(f"Too long: {duration:.1f}s")
        
        # Check resolution (RELAXED)
        if width < 320 or height < 240:
            reject_reasons.append(f"Resolution too low: {width}x{height}")
        
        # 2. Simple quality check
        quality_results = self.analyze_quality_simple(video_path)
        results.update(quality_results)
        
        if quality_results.get("blur_score", 0) < 10:
            reject_reasons.append(f"Too blurry: {quality_results['blur_score']:.1f}")
        
        # 3. Face detection (SIMPLIFIED)
        face_results = self.detect_faces_simple(video_path)
        results.update(face_results)
        
        # Accept if there's at least one face
        if face_results.get("face_count", 0) < 1:
            # Don't reject immediately - some videos might have faces at the end
            # Try checking more frames
            face_results2 = self.detect_faces_simple(video_path, sample_frames=30)
            if face_results2.get("face_count", 0) < 1:
                reject_reasons.append("No faces detected")
            else:
                results["face_count"] = face_results2["face_count"]
                results["average_face_size"] = face_results2["average_face_size"]
        
        # 4. Duplicate check (only if we have a hash)
        if self.is_duplicate(video_path, results):
            reject_reasons.append("Duplicate video")
        
        # Final decision
        passed = len(reject_reasons) == 0
        results["reject_reasons"] = reject_reasons
        
        return passed, results, ", ".join(reject_reasons) if reject_reasons else "Accepted"
    
    def analyze_quality_simple(self, video_path):
        """Simple quality analysis"""
        cap = cv2.VideoCapture(str(video_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total_frames == 0:
            return {"blur_score": 0, "quality_score": 0}
        
        # Sample frames
        sample_indices = np.linspace(0, total_frames - 1, min(5, total_frames), dtype=int)
        blur_scores = []
        
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                variance = cv2.Laplacian(gray, cv2.CV_64F).var()
                blur_scores.append(variance)
        
        cap.release()
        
        avg_blur = np.mean(blur_scores) if blur_scores else 0
        
        return {
            "blur_score": avg_blur,
            "quality_score": min(100, avg_blur / 2)
        }
    
    def detect_faces_simple(self, video_path, sample_frames=10):
        """Simple face detection"""
        cap = cv2.VideoCapture(str(video_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total_frames == 0:
            return {"face_count": 0, "average_face_size": 0}
        
        # Sample frames
        sample_indices = np.linspace(0, total_frames - 1, min(sample_frames, total_frames), dtype=int)
        
        face_sizes = []
        face_count_per_frame = []
        
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            
            h, w = frame.shape[:2]
            frame_area = h * w
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
            
            if len(faces) > 0:
                face_count_per_frame.append(len(faces))
                for (x, y, fw, fh) in faces:
                    face_area = fw * fh
                    face_sizes.append(face_area / frame_area)
        
        cap.release()
        
        avg_face_size = np.mean(face_sizes) if face_sizes else 0
        median_face_count = np.median(face_count_per_frame) if face_count_per_frame else 0
        
        return {
            "face_count": int(median_face_count),
            "average_face_size": avg_face_size,
            "max_face_size": max(face_sizes) if face_sizes else 0,
        }
    
    def is_duplicate(self, video_path, results):
        """Check for duplicates"""
        sha256 = self.calculate_sha256(video_path)
        results["sha256_hash"] = sha256
        
        # Simple duplicate check - just use the hash
        if sha256 in self.perceptual_hashes:
            return True
        
        self.perceptual_hashes.add(sha256)
        
        hash_file = Path("./metadata/perceptual_hashes.json")
        hash_file.parent.mkdir(parents=True, exist_ok=True)
        with open(hash_file, 'w') as f:
            json.dump(list(self.perceptual_hashes), f)
        
        return False
    
    def calculate_sha256(self, video_path):
        """Calculate SHA-256 hash"""
        sha256_hash = hashlib.sha256()
        with open(video_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def calculate_perceptual_hash(self, video_path):
        """Calculate perceptual hash from first frame"""
        cap = cv2.VideoCapture(str(video_path))
        ret, frame = cap.read()
        cap.release()
        
        if not ret or frame is None:
            return None
        
        resized = cv2.resize(frame, (8, 8))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        avg = np.mean(gray)
        hash_str = ''.join(['1' if pixel > avg else '0' for pixel in gray.flatten()])
        
        return hash_str