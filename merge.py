import os
import subprocess
import logging
import re
from datetime import timedelta

logger = logging.getLogger(__name__)

def get_video_duration(video_path):
    """Get precise video duration using ffprobe."""
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        output = subprocess.check_output(cmd, text=True).strip()
        return float(output)
    except:
        return 0.0

def parse_time(t_str):
    """Parse WEBVTT time string 'HH:MM:SS.mmm' or 'MM:SS.mmm' to seconds."""
    parts = re.split(r'[:.]', t_str)
    if len(parts) == 4: # HH:MM:SS.mmm
        h, m, s, ms = map(int, parts)
        return h * 3600 + m * 60 + s + ms / 1000.0
    elif len(parts) == 3: # MM:SS.mmm
        m, s, ms = map(int, parts)
        return m * 60 + s + ms / 1000.0
    return 0.0

def format_time(seconds):
    """Format seconds to WEBVTT time string 'HH:MM:SS.mmm'."""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    ms = int(td.microseconds / 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"

def format_time_srt(seconds):
    """Format seconds into SRT time string 'HH:MM:SS,mmm'."""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    ms = int(td.microseconds / 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def merge_episodes(video_dir: str, output_path: str):
    """
    Merges all eps into one, and includes subtitles as softsubs in SRT format.
    """
    try:
        files = sorted([f for f in os.listdir(video_dir) if f.endswith(".mp4")])
        if not files:
            return False
            
        list_file_path = os.path.join(video_dir, "list.txt")
        merged_srt_path = os.path.join(video_dir, "merged.srt")
        
        # 1. Merge & Convert Subtitles to SRT
        has_subtitles = False
        vtt_files = sorted([f for f in os.listdir(video_dir) if f.endswith(".vtt")])
        
        if vtt_files:
            logger.info("Merging and converting subtitles to SRT...")
            current_offset = 0.0
            with open(merged_srt_path, "w", encoding='utf-8') as out_f:
                counter = 1
                for v_file in files:
                    ep_num = v_file.split("_")[1].split(".")[0]
                    v_duration = get_video_duration(os.path.join(video_dir, v_file))
                    
                    s_file = f"episode_{ep_num}.vtt"
                    s_path = os.path.join(video_dir, s_file)
                    
                    if os.path.exists(s_path):
                        has_subtitles = True
                        with open(s_path, "r", encoding='utf-8') as in_f:
                            lines = in_f.readlines()
                            for line in lines:
                                if "-->" in line:
                                    times = re.findall(r'(\d+:\d+:\d+\.\d+|\d+:\d+\.\d+)', line)
                                    if len(times) >= 2:
                                        start = parse_time(times[0]) + current_offset
                                        end = parse_time(times[1]) + current_offset
                                        out_f.write(f"\n{counter}\n")
                                        out_f.write(f"{format_time_srt(start)} --> {format_time_srt(end)}\n")
                                        counter += 1
                                elif line.strip() == "" or line.strip() == "WEBVTT" or "NOTE" in line:
                                    continue
                                else:
                                    out_f.write(line)
                        out_f.write("\n")
                    current_offset += v_duration
            
        # 2. Merge Videos
        with open(list_file_path, "w") as f:
            for file in files:
                f.write(f"file '{file}'\n")

        temp_merged_video = os.path.join(video_dir, "temp_merged.mp4")
        command = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file_path, "-c", "copy",
            temp_merged_video
        ]
        
        logger.info(f"Merging videos: {' '.join(command)}")
        res = subprocess.run(command, capture_output=True)
        if res.returncode != 0 or not os.path.exists(temp_merged_video):
            logger.error(f"FFMPEG Concat failed.")
            return False

        # 3. Add softsubs with Indonesian Metadata
        if has_subtitles and os.path.exists(merged_srt_path):
            final_cmd = [
                "ffmpeg", "-y", "-i", temp_merged_video, "-i", merged_srt_path,
                "-c", "copy", "-c:s", "mov_text",
                "-metadata:s:s:0", "language=ind", 
                "-metadata:s:s:0", "handler_name=Indonesian",
                "-metadata:s:s:0", "title=Indonesian",
                output_path
            ]
            logger.info(f"Adding softsubs: {' '.join(final_cmd)}")
            res_sub = subprocess.run(final_cmd, capture_output=True)
            if res_sub.returncode != 0:
                 os.rename(temp_merged_video, output_path)
        else:
            os.rename(temp_merged_video, output_path)
            
        return os.path.exists(output_path)
    except Exception as e:
        logger.error(f"Error during merge: {e}")
        return False
