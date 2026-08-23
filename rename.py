from pathlib import Path
import shutil

# ==========================
# SETTINGS
# ==========================

source_folder = Path(r"D:\Saim\FYP 8th Semester\data\dataset\external\deepfake-detector\socialmedia-real")
destination_folder = Path(r"D:\Saim\FYP 8th Semester\data\dataset\external\deepfake-detector\socialmedia-real")

# Move videos bigger than this size
size_limit_kb = 230

# Base name for renamed files
base_name = "extsmreal0"

# Starting number
start_number = 1

video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

# ==========================
# SCRIPT
# ==========================

destination_folder.mkdir(parents=True, exist_ok=True)

size_limit_bytes = size_limit_kb * 1024

counter = start_number
moved = 0

for video_file in source_folder.rglob("*"):

    if not video_file.is_file():
        continue

    if video_file.suffix.lower() not in video_extensions:
        continue

    file_size = video_file.stat().st_size

    # Only process videos bigger than the limit
    if file_size > size_limit_bytes:

        # Keep the original extension
        extension = video_file.suffix.lower()

        # Create incremented filename
        new_filename = f"{base_name}_{counter}{extension}"
        destination = destination_folder / new_filename

        # Make sure we don't overwrite an existing file
        while destination.exists():
            counter += 1
            new_filename = f"{base_name}_{counter}{extension}"
            destination = destination_folder / new_filename

        # Move and rename
        shutil.move(str(video_file), str(destination))

        print(
            f"Moved: {video_file.name} "
            f"-> {new_filename} "
            f"({file_size / 1024:.2f} KB)"
        )

        counter += 1
        moved += 1

print("\nDone!")
print(f"Total videos moved: {moved}")