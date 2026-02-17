import customtkinter as ctk
from tkinter import messagebox, filedialog
import threading
import webbrowser
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

# --- Global Settings ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class PhotoMapperApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("askphotos.earth GTD Generator")
        self.geometry("750x850")
        self.is_running = False
        self.output_dir = os.getcwd()
        self.found_urls = []

        # Title
        self.lbl_title = ctk.CTkLabel(self, text="Ground-Truth Data Generator", font=("Roboto", 24, "bold"))
        self.lbl_title.pack(pady=(20, 2))

        self.lbl_subtitle = ctk.CTkLabel(self, text="askphotos.earth", font=("Roboto", 13), text_color="white", cursor="hand2")
        self.lbl_subtitle.pack(pady=(0, 10))
        self.lbl_subtitle.bind("<Button-1>", lambda e: webbrowser.open("https://askphotos.earth"))

        # 1. File & Location Section
        self.frame_top = ctk.CTkFrame(self)
        self.frame_top.pack(pady=10, fill="x", padx=50)
        
        # URL File
        self.btn_upload = ctk.CTkButton(self.frame_top, text="1. Upload the file (csv or txt) with the photo album's URLs", command=self.upload_file)
        self.btn_upload.grid(row=0, column=0, padx=10, pady=10)
        self.lbl_file = ctk.CTkLabel(self.frame_top, text="No file selected", text_color="gray")
        self.lbl_file.grid(row=0, column=1, padx=10, sticky="w")

        # Save Location
        self.btn_dir = ctk.CTkButton(self.frame_top, text="2. Select Save Folder", command=self.select_directory)
        self.btn_dir.grid(row=1, column=0, padx=10, pady=10)
        self.lbl_dir = ctk.CTkLabel(self.frame_top, text=f"Saving to: {self.output_dir[:40]}...", text_color="gray")
        self.lbl_dir.grid(row=1, column=1, padx=10, sticky="w")

        # 2. Options Frame
        self.frame_opts = ctk.CTkFrame(self)
        self.frame_opts.pack(pady=10, fill="x", padx=50)

        # Download Toggle
        self.check_download = ctk.CTkCheckBox(self.frame_opts, text="Compress & Download Images", command=self.update_visibility)
        self.check_download.pack(pady=10, padx=20, anchor="w")

        self.comp_container = ctk.CTkFrame(self.frame_opts, fg_color="transparent")
        self.lbl_comp = ctk.CTkLabel(self.comp_container, text="Compression. Select image quality (1-100%):")
        self.lbl_comp.pack(side="left", padx=20)
        self.entry_comp = ctk.CTkEntry(self.comp_container, width=80)
        self.entry_comp.insert(0, "70")
        self.entry_comp.pack(side="left")

        # AI Toggle
        self.check_ai = ctk.CTkCheckBox(self.frame_opts, text="Generate AI Semantics (Descriptions)", command=self.update_visibility)
        self.check_ai.pack(pady=10, padx=20, anchor="w")

        self.api_container = ctk.CTkFrame(self.frame_opts, fg_color="transparent")
        self.lbl_api_hint = ctk.CTkLabel(self.api_container, text="Create a key at: https://aistudio.google.com/api-keys. Other AI providers available soon" , text_color="#1a73e8", font=("Roboto", 11), cursor="hand2")
        self.lbl_api_hint.pack(pady=(0, 5))
        self.lbl_api_hint.bind("<Button-1>", lambda e: webbrowser.open("https://aistudio.google.com/api-keys"))
        
        self.api_input_row = ctk.CTkFrame(self.api_container, fg_color="transparent")
        self.api_input_row.pack()
        ctk.CTkLabel(self.api_input_row, text="API Key:").pack(side="left", padx=10)
        self.entry_api = ctk.CTkEntry(self.api_input_row, placeholder_text="Paste Key Here", width=300, show="*")
        self.entry_api.pack(side="left")

        # 3. Status and Controls
        self.lbl_status = ctk.CTkLabel(self, text="Status: Ready", font=("Roboto", 14), text_color="#1a73e8")
        self.lbl_status.pack(pady=(30, 5))

        # Scrollable frame for per-album progress bars
        self.progress_frame = ctk.CTkScrollableFrame(self, width=600, height=150, label_text="Album Progress")
        self.progress_frame.pack(pady=10, padx=50, fill="x")

        # Inline button row: START | STOP | VIEW MAP
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=10)

        self.btn_run = ctk.CTkButton(self.btn_frame, text="START", command=self.start_thread, height=45, width=150, font=("Roboto", 14, "bold"))
        self.btn_run.pack(side="left", padx=8)

        self.btn_stop = ctk.CTkButton(self.btn_frame, text="STOP", command=self.stop_process, height=45, width=150, font=("Roboto", 14, "bold"), fg_color="#d93025", hover_color="#b71c1c", state="disabled")
        self.btn_stop.pack(side="left", padx=8)

        self.btn_view_map = ctk.CTkButton(self.btn_frame, text="VIEW MAP", command=self.open_external_map, height=45, width=150, font=("Roboto", 14, "bold"), fg_color="gray40", hover_color="gray50", state="disabled")
        self.btn_view_map.pack(side="left", padx=8)

    def update_visibility(self):
        if self.check_download.get(): self.comp_container.pack(pady=5, fill="x")
        else: self.comp_container.pack_forget()

        if self.check_ai.get(): self.api_container.pack(pady=5, fill="x")
        else: self.api_container.pack_forget()

    def upload_file(self):
        f_path = filedialog.askopenfilename(filetypes=[
            ("Supported files", "*.txt *.csv"),
            ("Text files", "*.txt"),
            ("CSV files", "*.csv")
        ])
        if f_path:
            ext = os.path.splitext(f_path)[1].lower()
            if ext == ".csv":
                self.found_urls = self._extract_urls_from_csv(f_path)
            else:
                with open(f_path, "r", encoding="utf-8") as f:
                    self.found_urls = re.findall(r'https?://photos\.app\.goo\.gl/[^\s\n\r]+', f.read())
            self.lbl_file.configure(text=f"Found {len(self.found_urls)} URLs", text_color="white")

    def _extract_urls_from_csv(self, csv_path):
        """Scan every cell in a CSV file for Google Photos album URLs."""
        urls = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                for cell in row:
                    found = re.findall(r'https?://photos\.app\.goo\.gl/[^\s,"]+', cell)
                    urls.extend(found)
        return list(dict.fromkeys(urls))  # deduplicate while preserving order

    def select_directory(self):
        d_path = filedialog.askdirectory()
        if d_path:
            self.output_dir = d_path
            self.lbl_dir.configure(text=f"Saving to: {d_path[:40]}...")

    def stop_process(self):
        self.is_running = False
        self.update_status("Stopping...", "orange")

    def open_external_map(self):
        webbrowser.open("https://askphotos.earth/pages/viewer.html")

    def start_thread(self):
        if not self.found_urls:
            messagebox.showwarning("Warning", "Please upload a .txt or .csv file first.")
            return
        self.is_running = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_view_map.configure(state="disabled", fg_color="gray40", hover_color="gray50")
        # Clear previous album progress bars
        for widget in self.progress_frame.winfo_children():
            widget.destroy()
        threading.Thread(target=self.main_logic, daemon=True).start()

    def add_album_progress(self, album_idx):
        """Create a label + progress bar for an album and return them."""
        frame = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        frame.pack(fill="x", pady=5, padx=5)
        lbl = ctk.CTkLabel(frame, text=f"Album {album_idx}: Loading...", font=("Roboto", 12))
        lbl.pack(anchor="w")
        bar = ctk.CTkProgressBar(frame, width=500)
        bar.set(0)
        bar.pack(fill="x", pady=(2, 0))
        return lbl, bar

    def save_geojson(self, features):
        """Write current features to the geojson file."""
        geojson_path = os.path.join(self.output_dir, "photos.geojson")
        with open(geojson_path, "w") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f)

    def main_logic(self):
        photo_dir = os.path.join(self.output_dir, "photos")
        if not os.path.exists(photo_dir): os.makedirs(photo_dir)
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        features = []
        global_idx = 0
        do_download = self.check_download.get()

        client = None
        if self.check_ai.get():
            api_key = self.entry_api.get().strip()
            if not api_key:
                self.update_status("Error: API Key missing!", "red")
                self.reset_ui()
                return
            client = genai.Client(api_key=api_key)

        try:
            for album_num, album_url in enumerate(self.found_urls, start=1):
                if not self.is_running: break

                # Create per-album progress bar
                album_lbl, album_bar = self.add_album_progress(album_num)
                album_lbl.configure(text=f"Album {album_num}: Fetching links...")

                res = requests.get(album_url, headers=headers, timeout=15)
                img_links = list(set(re.findall(r'\"(https://lh3\.googleusercontent\.com/pw/[^\"]+)\"', res.text)))
                
                total = len(img_links)
                album_lbl.configure(text=f"Album {album_num}: Scanning...")
                geo_count = 0  # Count of images with location metadata
                valid_count = 0  # Count of images >= 10KB

                for i, link in enumerate(img_links):
                    if not self.is_running: break
                    time.sleep(random.uniform(1.2, 2.2))

                    img_res = requests.get(link + "=d", headers=headers, stream=True)
                    if img_res.status_code == 200:
                        content = img_res.content
                        if len(content) < 10240: continue  # Skip < 10KB

                        valid_count += 1
                        self.update_status(f"Album {album_num} — Scanning {valid_count}")
                        album_bar.set((i+1)/total if total > 0 else 1)
                        album_lbl.configure(text=f"Album {album_num}: Scanning {valid_count} ({geo_count} with location)")

                        # Extract metadata (GPS + date) from bytes — no file needed
                        coords, date_taken = self.get_metadata(content)
                        if not coords:
                            continue

                        geo_count += 1
                        global_idx += 1
                        album_lbl.configure(text=f"Album {album_num}: Scanning {valid_count} ({geo_count} with location)")

                        # AI description
                        desc = "No AI-generated Semantics"
                        if self.check_ai.get():
                            try:
                                self.update_status(f"Album {album_num} — Analysing Image {geo_count} Semantics...")
                                p = types.Part.from_bytes(data=content, mime_type="image/jpeg")
                                ai_out = client.models.generate_content(model="gemini-2.0-flash", contents=["Short description.", p])
                                desc = ai_out.text.strip()
                            except: desc = "AI Analysis Error"

                        # Only save to disk when download is checked
                        if do_download:
                            save_path = os.path.join(photo_dir, f"img_{global_idx}.jpg")
                            try:
                                q = int(self.entry_comp.get())
                                img = Image.open(BytesIO(content))
                                img.save(save_path, "JPEG", quality=q, optimize=True)
                            except:
                                with open(save_path, 'wb') as f:
                                    f.write(content)

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

                # Album finished — mark complete and save geojson incrementally
                if self.is_running:
                    album_bar.set(1.0)
                    album_lbl.configure(text=f"Album {album_num}: ✓ Done ({geo_count} geo-tagged out of {valid_count})", text_color="#4BB543")
                    self.save_geojson(features)
                    # Enable VIEW MAP in yellow (data available but still processing)
                    self.btn_view_map.configure(state="normal", fg_color="#E8A317", hover_color="#C4900A")

            if self.is_running:
                self.update_status("Done!", "#4BB543")
                # All albums complete — turn VIEW MAP green
                self.btn_view_map.configure(state="normal", fg_color="#4BB543", hover_color="#3e9436")
            else:
                self.save_geojson(features)
                self.update_status("Stopped", "orange")

        except Exception as e:
            self.update_status(f"Error: {str(e)}", "red")
        finally:
            self.reset_ui()

    def reset_ui(self):
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def update_status(self, msg, color="white"):
        self.lbl_status.configure(text=f"Status: {msg}", text_color=color)

    def get_metadata(self, content):
        """Extract GPS coordinates and date-taken from image bytes."""
        try:
            t = exifread.process_file(BytesIO(content))
            def c(v): return float(v.values[0].num)/float(v.values[0].den) + \
                             float(v.values[1].num)/float(v.values[1].den)/60 + \
                             float(v.values[2].num)/float(v.values[2].den)/3600
            lat = c(t['GPS GPSLatitude'])
            if t['GPS GPSLatitudeRef'].values[0] != 'N': lat = -lat
            lon = c(t['GPS GPSLongitude'])
            if t['GPS GPSLongitudeRef'].values[0] not in ['E', 'East']: lon = -lon
            coords = (lat, lon)
        except:
            return None, None

        date_taken = None
        for tag in ['EXIF DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime']:
            if tag in t:
                date_taken = str(t[tag])
                break

        return coords, date_taken

if __name__ == "__main__":
    app = PhotoMapperApp()
    app.mainloop()
