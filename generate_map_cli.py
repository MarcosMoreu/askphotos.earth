import argparse
import requests
import re
import os
import json
import csv
import exifread
import time
import random
from io import BytesIO
from PIL import Image
from google import genai
from google.genai import types
from tqdm import tqdm

def get_metadata(content):
    """Extract GPS and date-taken from image bytes."""
    try:
        t = exifread.process_file(BytesIO(content))
        def c(v): return float(v.values[0].num)/float(v.values[0].den) + \
                         float(v.values[1].num)/float(v.values[1].den)/60 + \
                         float(v.values[2].num)/float(v.values[2].den)/3600
        lat = c(t['GPS GPSLatitude'])
        if t['GPS GPSLatitudeRef'].values[0] != 'N': lat = -lat
        lon = c(t['GPS GPSLongitude'])
        if t['GPS GPSLongitudeRef'].values[0] not in ['E', 'East']: lon = -lon
        
        date_taken = None
        for tag in ['EXIF DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime']:
            if tag in t:
                date_taken = str(t[tag])
                break
        return (lat, lon), date_taken
    except:
        return None, None

def main():
    parser = argparse.ArgumentParser(description="askphotos.earth GTD Generator (CLI Version)")
    parser.add_argument("--file", required=True, help="Path to .txt or .csv file with Google Photos URLs")
    parser.add_argument("--out", default=".", help="Output directory (default: current)")
    parser.add_argument("--download", action="store_true", help="Compress and download images")
    parser.add_argument("--quality", type=int, default=70, help="Image quality (1-100)")
    parser.add_argument("--key", help="Google AI API Key for semantics")
    args = parser.parse_args()

    # Setup directories
    if not os.path.exists(args.out): os.makedirs(args.out)
    photo_dir = os.path.join(args.out, "photos")
    if args.download and not os.path.exists(photo_dir): os.makedirs(photo_dir)

    # Load URLs from file (.txt or .csv)
    ext = os.path.splitext(args.file)[1].lower()
    if ext == ".csv":
        urls = []
        with open(args.file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                for cell in row:
                    found = re.findall(r'https?://photos\.app\.goo\.gl/[^\s,"]+', cell)
                    urls.extend(found)
        urls = list(dict.fromkeys(urls))  # deduplicate preserving order
    else:
        with open(args.file, "r", encoding="utf-8") as f:
            urls = re.findall(r'https?://photos\.app\.goo\.gl/[^\s\n\r]+', f.read())

    client = genai.Client(api_key=args.key) if args.key else None
    features = []
    global_idx = 0

    print(f"🚀 Found {len(urls)} albums. Starting process...")

    for a_idx, album_url in enumerate(urls, 1):
        try:
            res = requests.get(album_url, timeout=15)
            img_links = list(set(re.findall(r'\"(https://lh3\.googleusercontent\.com/pw/[^\"]+)\"', res.text)))
            
            # Use tqdm for a terminal progress bar
            for link in tqdm(img_links, desc=f"Album {a_idx}", unit="img"):
                time.sleep(random.uniform(1.2, 2.2)) # Stealth delay
                
                img_res = requests.get(link + "=d", stream=True)
                if img_res.status_code == 200:
                    content = img_res.content
                    if len(content) < 10240: continue # Skip < 10KB
                    
                    coords, date_taken = get_metadata(content)
                    if not coords: continue

                    global_idx += 1
                    desc = "No AI-generated Semantics"
                    
                    if client:
                        try:
                            p = types.Part.from_bytes(data=content, mime_type="image/jpeg")
                            ai_out = client.models.generate_content(model="gemini-3.1-flash-lite", contents=["Short description.", p])
                            desc = ai_out.text.strip()
                        except: desc = "AI Error"

                    if args.download:
                        save_path = os.path.join(photo_dir, f"img_{global_idx}.jpg")
                        img = Image.open(BytesIO(content))
                        img.save(save_path, "JPEG", quality=args.quality, optimize=True)

                    features.append({
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [coords[1], coords[0]]},
                        "properties": {
                            "album": album_url,
                            "url": link,
                            "desc": desc,
                            "date": date_taken or "Unknown"
                        }
                    })
        except Exception as e:
            print(f"❌ Error processing album {a_idx}: {e}")

    # Final Save
    output_file = os.path.join(args.out, "photos.geojson")
    with open(output_file, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)
    
    print(f"\n✅ Done! {global_idx} images mapped. File saved to: {output_file}")

if __name__ == "__main__":
    main()
