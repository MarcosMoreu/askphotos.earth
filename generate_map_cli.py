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

# Enable HEIC/HEIF support in Pillow. If the package isn't installed the script
# still works for JPEG; only HEIF files will be skipped.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:
    HEIF_OK = False


def _ensure_jpeg(content):
    """Return JPEG bytes for any input. Re-encodes HEIC/HEIF/PNG/etc.;
    leaves an existing JPEG untouched to avoid a needless quality loss."""
    img = Image.open(BytesIO(content))
    if (img.format or "").upper() in ("JPEG", "JPG"):
        return content
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()

def get_metadata(content):
    """Extract GPS and date-taken from image bytes.
    Tries exifread first (JPEG/TIFF); falls back to Pillow for HEIC/HEIF."""
    coords, date_taken = _metadata_exifread(content)
    if coords:
        return coords, date_taken
    return _metadata_pillow(content)

def _metadata_exifread(content):
    """Original exifread path — fast and reliable for JPEG/TIFF."""
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

def _metadata_pillow(content):
    """Pillow-based extractor. Works for HEIC/HEIF (via pillow-heif) and any
    other format Pillow can open. Reads EXIF from the ORIGINAL bytes so GPS is
    never lost to a format conversion."""
    try:
        img = Image.open(BytesIO(content))
        exif = img.getexif()
        if not exif:
            return None, None

        gps = exif.get_ifd(0x8825)   # GPS IFD
        if not gps:
            return None, None

        def to_deg(rationals):
            d, m, s = rationals
            return float(d) + float(m) / 60.0 + float(s) / 3600.0

        lat_val = gps.get(2)   # GPSLatitude  (deg, min, sec)
        lon_val = gps.get(4)   # GPSLongitude
        if not lat_val or not lon_val:
            return None, None

        lat = to_deg(lat_val)
        lon = to_deg(lon_val)
        if str(gps.get(1, 'N')).upper().startswith('S'):   # GPSLatitudeRef
            lat = -lat
        if str(gps.get(3, 'E')).upper().startswith('W'):   # GPSLongitudeRef
            lon = -lon

        date_taken = None
        exif_ifd = exif.get_ifd(0x8769)   # Exif sub-IFD
        for tag_id in (36867, 36868):     # DateTimeOriginal / DateTimeDigitized
            if exif_ifd.get(tag_id):
                date_taken = str(exif_ifd.get(tag_id))
                break
        if not date_taken and exif.get(306):   # Image DateTime
            date_taken = str(exif.get(306))

        return (lat, lon), date_taken
    except Exception:
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
            
            # Progress bar counts only real images: the sub-10KB thumbnails/junk
            # that get skipped no longer advance it. The valid total isn't known
            # up front (size is only known after download), so the bar runs as an
            # indeterminate counter rather than a percentage.
            skipped = 0
            album_geo = 0  # images in this album that carry GPS location
            pbar = tqdm(desc=f"Album {a_idx}  {album_url}", unit="img")
            for link in img_links:
                time.sleep(random.uniform(0.3, 0.6)) # Stealth delay

                img_res = requests.get(link + "=d", stream=True)
                if img_res.status_code != 200:
                    continue

                content = img_res.content
                if len(content) < 10240:
                    skipped += 1
                    continue # Skip < 10KB (not shown in the bar)

                pbar.update(1)  # real image — advance the bar

                coords, date_taken = get_metadata(content)
                if not coords: continue

                album_geo += 1
                global_idx += 1
                desc = "No AI-generated Semantics"

                if client:
                    try:
                        jpeg_bytes = _ensure_jpeg(content)
                        p = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
                        ai_out = client.models.generate_content(model="gemini-3.1-flash-lite", contents=["Short description.", p])
                        desc = ai_out.text.strip()
                    except: desc = "AI Error"

                if args.download:
                    save_path = os.path.join(photo_dir, f"img_{global_idx}.jpg")
                    img = Image.open(BytesIO(content))
                    if img.mode not in ("RGB", "L"):
                        img = img.convert("RGB")
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

            pbar.close()
            scanned = int(pbar.n)
            summary = f"   \u21b3 Album {a_idx}: {album_geo}/{scanned} images with location"
            if skipped:
                summary += f"  ({skipped} sub-10KB thumbnails skipped)"
            tqdm.write(summary)
        except Exception as e:
            print(f"❌ Error processing album {a_idx}: {e}")

    # Final Save
    output_file = os.path.join(args.out, "photos.geojson")
    with open(output_file, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)
    
    print(f"\n✅ Done! {global_idx} images mapped. File saved to: {output_file}. Drag & drop this file into https://askphotos.earth/pages/viewer to explore the map, or add it to your GIS software for deeper analysis.")

if __name__ == "__main__":
    main()
