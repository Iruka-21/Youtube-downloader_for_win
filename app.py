import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from tkinter import filedialog
import urllib.request
import zipfile
import customtkinter as ctk
import yt_dlp

# 外観テーマ設定
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# アプリ実行ディレクトリのパス解決（exe化対応）
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APP_DIR, "downloader_config.json")
FFMPEG_DIR = os.path.join(APP_DIR, "bin")


class YouTubeDownloaderPro(ctk.CTk):

    def __init__(self):
        super().__init__()

        # ウィンドウ設定（どんなモニターでも見やすいサイズ）
        self.title("YouTube Batch Downloader Ultimate")
        self.geometry("720x680")
        self.resizable(False, False)

        # 内部状態
        self.is_downloading = False
        self.cancel_requested = False
        self.download_dir = self.load_saved_dir()
        self.ffmpeg_path = self.detect_ffmpeg()

        self.create_widgets()

        # FFmpegが存在しない場合は起動時に自動取得
        if not self.ffmpeg_path:
            self.start_ffmpeg_setup()

    def detect_ffmpeg(self):
        """システムまたはbinフォルダからFFmpegを検出"""
        ext = ".exe" if platform.system() == "Windows" else ""
        local_ffmpeg = os.path.join(FFMPEG_DIR, f"ffmpeg{ext}")
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg
        return shutil.which("ffmpeg")

    def load_saved_dir(self):
        """保存先設定の読み込み"""
        default_path = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f).get("download_dir", default_path)
            except Exception:
                pass
        return default_path

    def save_dir_setting(self, path):
        """保存先設定を書き込み"""
        self.download_dir = path
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"download_dir": path}, f, ensure_ascii=False, indent=2)

    def log(self, message):
        """リアルタイムログコンソールへの出力"""
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert(
            "end", f"[{time.strftime('%H:%M:%S')}] {message}\n"
        )
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def create_widgets(self):
        # 1. ヘッダー
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(padx=20, pady=(10, 4), fill="x")

        title = ctk.CTkLabel(
            header,
            text="YouTube 一括ダウンローダー Pro",
            font=("Helvetica", 18, "bold"),
        )
        title.pack(side="left")

        update_btn = ctk.CTkButton(
            header,
            text="エンジン最新化",
            width=105,
            height=28,
            command=self.start_update_ytdlp,
        )
        update_btn.pack(side="right")

        # 2. URL入力エリア
        url_top = ctk.CTkFrame(self, fg_color="transparent")
        url_top.pack(padx=20, pady=(2, 2), fill="x")

        ctk.CTkLabel(
            url_top,
            text="URL一覧 (1行に1つ / プレイリスト対応):",
            font=("Helvetica", 12, "bold"),
        ).pack(side="left")

        clear_btn = ctk.CTkButton(
            url_top,
            text="クリア",
            width=50,
            height=22,
            fg_color="gray",
            hover_color="dimgray",
            command=lambda: self.url_textbox.delete("1.0", "end"),
        )
        clear_btn.pack(side="right", padx=(4, 0))

        paste_btn = ctk.CTkButton(
            url_top,
            text="クリップボード貼付",
            width=110,
            height=22,
            command=self.paste_from_clipboard,
        )
        paste_btn.pack(side="right", padx=(4, 0))

        load_file_btn = ctk.CTkButton(
            url_top,
            text="テキスト読込(.txt)",
            width=110,
            height=22,
            command=self.load_from_txt,
        )
        load_file_btn.pack(side="right")

        self.url_textbox = ctk.CTkTextbox(self, width=680, height=95)
        self.url_textbox.pack(padx=20, pady=(2, 5))

        # 3. オプション設定
        options_frame = ctk.CTkFrame(self)
        options_frame.pack(padx=20, pady=4, fill="x")

        ctk.CTkLabel(
            options_frame, text="画質設定:", font=("Helvetica", 12)
        ).grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.quality_var = ctk.StringVar(value="最高画質 (自動)")
        self.quality_combo = ctk.CTkComboBox(
            options_frame,
            values=[
                "最高画質 (自動)",
                "1080p (Full HD)",
                "720p (HD)",
                "480p (SD)",
                "音声のみ (MP3)",
            ],
            variable=self.quality_var,
            width=140,
            height=26,
        )
        self.quality_combo.grid(row=0, column=1, padx=5, pady=6)

        self.embed_thumb_var = ctk.BooleanVar(value=True)
        self.thumb_chk = ctk.CTkCheckBox(
            options_frame,
            text="サムネイル埋め込み",
            variable=self.embed_thumb_var,
            checkbox_width=20,
            checkbox_height=20,
        )
        self.thumb_chk.grid(row=0, column=2, padx=12, pady=6)

        self.subtitles_var = ctk.BooleanVar(value=False)
        self.sub_chk = ctk.CTkCheckBox(
            options_frame,
            text="字幕取得 (日/英)",
            variable=self.subtitles_var,
            checkbox_width=20,
            checkbox_height=20,
        )
        self.sub_chk.grid(row=0, column=3, padx=10, pady=6)

        # 4. 保存先フォルダ
        folder_frame = ctk.CTkFrame(self)
        folder_frame.pack(padx=20, pady=4, fill="x")

        self.folder_label = ctk.CTkLabel(
            folder_frame,
            text=f"保存先: {self.download_dir}",
            anchor="w",
            text_color="gray",
            font=("Helvetica", 11),
        )
        self.folder_label.pack(
            side="left", padx=12, pady=6, fill="x", expand=True
        )

        open_folder_btn = ctk.CTkButton(
            folder_frame,
            text="フォルダを開く",
            width=90,
            height=26,
            command=self.open_download_folder,
        )
        open_folder_btn.pack(side="right", padx=(4, 8), pady=6)

        select_folder_btn = ctk.CTkButton(
            folder_frame,
            text="保存先変更",
            width=80,
            height=26,
            command=self.select_folder,
        )
        select_folder_btn.pack(side="right", padx=4, pady=6)

        # 5. アクションボタン（開始 / 中断）
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(padx=20, pady=6, fill="x")

        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="ダウンロード開始",
            height=36,
            font=("Helvetica", 14, "bold"),
            command=self.start_download_thread,
        )
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.cancel_btn = ctk.CTkButton(
            btn_frame,
            text="中断",
            height=36,
            width=80,
            fg_color="crimson",
            hover_color="darkred",
            state="disabled",
            command=self.request_cancel,
        )
        self.cancel_btn.pack(side="right", padx=(5, 0))

        # 6. 進捗状況エリア (ダブル進捗バー)
        progress_box = ctk.CTkFrame(self)
        progress_box.pack(padx=20, pady=4, fill="x")

        self.overall_label = ctk.CTkLabel(
            progress_box,
            text="全体進捗: 待機中",
            font=("Helvetica", 11, "bold"),
        )
        self.overall_label.pack(anchor="w", padx=10, pady=(4, 0))
        self.overall_bar = ctk.CTkProgressBar(progress_box, width=660, height=9)
        self.overall_bar.set(0)
        self.overall_bar.pack(padx=10, pady=(2, 4))

        self.current_label = ctk.CTkLabel(
            progress_box,
            text="現在のプロセス: 待機中",
            font=("Helvetica", 11),
            text_color="dodgerblue",
        )
        self.current_label.pack(anchor="w", padx=10, pady=(1, 0))
        self.current_bar = ctk.CTkProgressBar(progress_box, width=660, height=9)
        self.current_bar.set(0)
        self.current_bar.pack(padx=10, pady=(2, 6))

        # 7. リアルタイムログコンソール
        ctk.CTkLabel(
            self,
            text="処理プロセス リアルタイムログ:",
            font=("Helvetica", 11, "bold"),
        ).pack(anchor="w", padx=20, pady=(4, 0))
        self.log_textbox = ctk.CTkTextbox(
            self,
            width=680,
            height=130,
            font=("Consolas", 10),
            state="disabled",
        )
        self.log_textbox.pack(padx=20, pady=(2, 8))

    # ==================== 補助操作 ====================
    def paste_from_clipboard(self):
        try:
            text = self.clipboard_get()
            self.url_textbox.insert("end", text.strip() + "\n")
        except Exception:
            pass

    def load_from_txt(self):
        path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.url_textbox.insert("end", f.read().strip() + "\n")
            except Exception as e:
                self.log(f"ファイル読込エラー: {e}")

    def select_folder(self):
        path = filedialog.askdirectory(initialdir=self.download_dir)
        if path:
            self.save_dir_setting(path)
            self.folder_label.configure(text=f"保存先: {path}")

    def open_download_folder(self):
        if os.path.exists(self.download_dir):
            if platform.system() == "Windows":
                os.startfile(self.download_dir)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", self.download_dir])
            else:
                subprocess.Popen(["xdg-open", self.download_dir])

    def request_cancel(self):
        if self.is_downloading:
            self.cancel_requested = True
            self.log("⚠️ ダウンロード中断を要求しました...")
            self.cancel_btn.configure(state="disabled")

    # ==================== アップデート / FFmpeg ====================
    def start_update_ytdlp(self):
        self.log("yt-dlp エンジンを最新版に更新中...")
        threading.Thread(target=self._update_ytdlp_thread, daemon=True).start()

    def _update_ytdlp_thread(self):
        try:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "yt-dlp",
                ]
            )
            self.log("✅ エンジンを最新版に更新しました！")
        except Exception as e:
            self.log(f"❌ 更新失敗: {e}")

    def start_ffmpeg_setup(self):
        self.start_btn.configure(state="disabled")
        self.log("初回セットアップ: FFmpegをダウンロードしています...")
        threading.Thread(target=self._download_ffmpeg, daemon=True).start()

    def _download_ffmpeg(self):
        try:
            os.makedirs(FFMPEG_DIR, exist_ok=True)
            if platform.system() == "Windows":
                url = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
                zip_path = os.path.join(FFMPEG_DIR, "ffmpeg.zip")

                def hook(b_num, b_size, t_size):
                    if t_size > 0:
                        self.current_bar.set((b_num * b_size) / t_size)

                urllib.request.urlretrieve(url, zip_path, reporthook=hook)

                with zipfile.ZipFile(zip_path, "r") as zf:
                    for member in zf.namelist():
                        if member.endswith("ffmpeg.exe") or member.endswith(
                            "ffprobe.exe"
                        ):
                            filename = os.path.basename(member)
                            with zf.open(member) as src, open(
                                os.path.join(FFMPEG_DIR, filename), "wb"
                            ) as dst:
                                shutil.copyfileobj(src, dst)

                if os.path.exists(zip_path):
                    os.remove(zip_path)

            self.ffmpeg_path = self.detect_ffmpeg()
            self.current_bar.set(0)
            self.log("✅ FFmpegセットアップ完了！")
            self.start_btn.configure(state="normal")
        except Exception as e:
            self.log(f"❌ FFmpeg取得エラー: {e}")
            self.start_btn.configure(state="normal")

    # ==================== ダウンロード本体 ====================
    def start_download_thread(self):
        if self.is_downloading:
            return
        threading.Thread(target=self.run_batch_download, daemon=True).start()

    def progress_hook(self, d):
        if self.cancel_requested:
            raise Exception("ユーザーによって中断されました")

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed", 0)
            eta = d.get("eta", 0)

            speed_str = (
                f"{speed / (1024*1024):.1f} MB/s" if speed else "-- MB/s"
            )
            eta_str = f"残り {eta}秒" if eta else ""

            info = d.get("info_dict", {})
            vcodec = info.get("vcodec", "none")
            kind = "音声" if vcodec == "none" else "映像"

            if total > 0:
                percent = downloaded / total
                self.current_bar.set(percent)
                self.current_label.configure(
                    text=f"[{kind}受信中] {percent*100:.1f}% ({speed_str} | {eta_str})"
                )
        elif status == "finished":
            self.current_label.configure(
                text="[処理中] ダウンロード完了。結合・変換を行っています..."
            )
            self.current_bar.set(1.0)

    def postprocessor_hook(self, d):
        status = d.get("status")
        pp = d.get("postprocessor", "")
        if status == "started":
            if "ExtractAudio" in pp:
                self.log("⚙️ 音声抽出・MP3変換処理を開始...")
            elif "FFmpegMerger" in pp or "Merger" in pp:
                self.log("⚙️ FFmpegで映像と音声を結合中...")
            elif "EmbedThumbnail" in pp:
                self.log("🖼️ サムネイル画像を埋め込み中...")
        elif status == "finished":
            self.log(f"✅ 後処理完了: {pp}")

    def run_batch_download(self):
        raw_text = self.url_textbox.get("1.0", "end").strip()
        urls = [line.strip() for line in raw_text.splitlines() if line.strip()]

        if not urls:
            self.log("⚠️ URLが入力されていません。")
            return

        self.is_downloading = True
        self.cancel_requested = False
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")

        quality = self.quality_var.get()
        embed_thumb = self.embed_thumb_var.get()
        get_subtitles = self.subtitles_var.get()

        # フォーマット & 後処理設定
        postprocessors = []
        if quality == "音声のみ (MP3)":
            format_opts = {"format": "bestaudio/best"}
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            )
        else:
            limit = {
                "1080p (Full HD)": 1080,
                "720p (HD)": 720,
                "480p (SD)": 480,
            }.get(quality)
            f_str = (
                f"bestvideo[height<={limit}]+bestaudio/best[height<={limit}]"
                if limit
                else "bestvideo+bestaudio/best"
            )
            format_opts = {"format": f_str, "merge_output_format": "mp4"}

        # サムネイル埋め込み設定
        if embed_thumb:
            postprocessors.append({"key": "EmbedThumbnail"})
            if quality != "音声のみ (MP3)":
                postprocessors.append({"key": "FFmpegMetadata"})

        outtmpl_pattern = os.path.join(
            self.download_dir,
            "%(playlist_title&{}/|)s%(playlist_index&{:02d}_|)s%(title)s.%(ext)s".format(
                "%(playlist_title)s", "%(playlist_index)d"
            ),
        )

        ydl_opts = {
            "outtmpl": outtmpl_pattern,
            "progress_hooks": [self.progress_hook],
            "postprocessor_hooks": [self.postprocessor_hook],
            "postprocessors": postprocessors,
            "writethumbnail": embed_thumb,
            "windowsfilenames": True,  # 安全なファイル名サニタイズ（日本語対応）
            "restrictfilenames": False,
            "ignoreerrors": True,
            # 安全な公開クライアント偽装（ブラウザデータ参照なし）
            "extractor_args": {
                "youtube": {"player_client": ["tv", "web_safari", "android"]}
            },
            "socket_timeout": 30,
            "retries": 10,
            "fragment_retries": 10,
            **format_opts,
        }

        # 字幕設定
        if get_subtitles:
            ydl_opts["writesubtitles"] = True
            ydl_opts["subtitleslangs"] = ["ja", "en"]
            ydl_opts["subtitlesformat"] = "srt"

        if self.ffmpeg_path:
            ydl_opts["ffmpeg_location"] = os.path.dirname(self.ffmpeg_path)

        total_urls = len(urls)
        success_count = 0

        self.log(f"🚀 一括ダウンロード開始 (全 {total_urls} 件)")

        for i, url in enumerate(urls, start=1):
            if self.cancel_requested:
                self.log("🛑 処理を中断しました。")
                break

            self.overall_bar.set((i - 1) / total_urls)
            self.overall_label.configure(
                text=f"全体進捗: [{i}/{total_urls}] 件目を処理中..."
            )
            self.current_label.configure(text="[解析中] 動画情報を取得中...")
            self.current_bar.set(0)

            self.log(f"▶ [{i}/{total_urls}] 解析中: {url}")

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                success_count += 1
                self.log(f"✔ [{i}/{total_urls}] 完了！")
            except Exception as e:
                if self.cancel_requested:
                    self.log("🛑 処理が中断されました。")
                    break
                self.log(f"❌ エラー (スキップ): {str(e)[:40]}")

        self.overall_bar.set(1.0 if not self.cancel_requested else 0)
        self.current_bar.set(0)
        self.overall_label.configure(
            text=f"処理完了: {success_count}/{total_urls} 件 成功"
        )
        self.current_label.configure(text="現在のプロセス: 待機中")

        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.is_downloading = False
        self.cancel_requested = False


if __name__ == "__main__":
    app = YouTubeDownloaderPro()
    app.mainloop()
