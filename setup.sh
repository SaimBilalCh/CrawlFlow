#!/bin/bash

echo "🔧 Setting up Deepfake Data Collector..."

# Create directories
mkdir -p downloads metadata logs cookies credentials

# Install dependencies
pip install -r requirements.txt

echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Get Google Drive credentials.json from Google Cloud Console"
echo "2. Place it in credentials/ folder"
echo "3. Add DRIVE_FOLDER_ID to your .env file"
echo "4. Export cookies from TikTok/Instagram/YouTube to cookies/"
echo "5. Run: python main.py"