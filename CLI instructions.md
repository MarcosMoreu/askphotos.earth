# askphotos.earth Ground-truth Data Generator (CLI)

## 🛠 Step 1: Install Python
Before running the script, you must have Python installed.
1. Download Python from [python.org](https://www.python.org/downloads/).

---

## 📥 Step 2: Save the Script to Your Machine
You need the processing script and a list of links to begin.

1. **Create a Folder:** Create a new folder on your computer named e.g. `AskPhotos`.
2. **Save the Script:** Save the `generate_map_cli.py` file inside that folder. 
https://github.com/MarcosMoreu/GTDGenerator-askphotosdotearth/blob/main/generate_map_cli.py
3. **Prepare Your Links:** Create a text file in the same folder named `links.txt`. Paste the Google Photos shared albums URLs inside it. The script will exclude any text inside the file except these URLs. For instance, you can upload a exported WhatsApp group chat and the GTD Generator will find the Google Photos URLs only.   

---

## 📦 Step 3: Install Required Libraries
Open your terminal and run the following command to install the necessary tools:

1. Pillow: Handles image opening and quality compression.
2. requests: Downloads the images and album data from Google's servers.
3. exifread: Reads the hidden GPS and timestamp data inside your photos.
4. google-genai (Optional): Connects to Google's Gemini AI to generate semantic descriptions.

```bash
pip install Pillow requests exifread google-genai
```

## 🚀 Step 4: Run the Generator
In your terminal, navigate to your AskPhotos folder and run one of the following commands (change python3 version if different):

Basic Map Generation (Fastest)
This scans your links and creates a map file without downloading photos or using AI.

```bash
python3 generate_map_cli.py --file links.txt
```
Full Data Generation (Download + AI)
This compresses/saves images locally and uses AI to describe each photo. Create a key at: https://aistudio.google.com/api-keys. Other AI providers available soon.

```bash
python3 generate_map_cli.py --file links.txt --download --quality 70 --key YOUR_GOOGLE_AI_KEY
```
📝 Command Options

1. download	Include this flag if you want to save local compressed copies of the photos. ❗ Keep in mind the local storage available when activating this option.
2. quality	Set the image compression quality from 1-100 (70 is recommended). 
3. key	Your Google Gemini API Key. Get one for free at AI Studio. ❗ Keep in mind the costs when activating this option

## 🗺 Step 5: Visualize
Once the process is complete, a photos.geojson file will appear in your folder.

Go to https://askphotos.earth/pages/viewer. Drag and drop the photos.geojson file onto the map to see your journey!

