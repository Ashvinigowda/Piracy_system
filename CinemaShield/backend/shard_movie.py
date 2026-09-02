import os
import subprocess
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

UPLOAD_FOLDER = "uploads"
SHARD_FOLDER = "shards"

SHARD_SIZE_MB = 1                          # Target size per shard (1 MB for high-granularity sharding)
SHARD_SIZE_BYTES = SHARD_SIZE_MB * 1024 * 1024
MIN_SHARDS = 6                             # High fragmentation: minimum 6 shards

os.makedirs(SHARD_FOLDER, exist_ok=True)


def calculate_shards(file_path):
    """
    Each shard targets ~1 MB. E.g. a 50 MB file → 50 shards.
    More shards = higher fragmentation across the multi-cloud storage mesh.
    """
    file_size = os.path.getsize(file_path)
    return max(MIN_SHARDS, math.ceil(file_size / SHARD_SIZE_BYTES))


def get_video_duration(file_path):
    """Returns video duration in seconds (float)."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(result.stdout.strip())


def _extract_shard(file_path, index, start_time, duration, output_path):
    """
    Extract a single shard using input-seeking + stream copy.
    -ss before -i uses keyframe-level seeking (near-instant for any offset).
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),          # input seek — fast, uses index
        "-i", file_path,
        "-t", str(duration),              # limit length
        "-c", "copy",                     # no re-encode
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def shard_video(file_path):
    """
    High-Performance Sharder:
    1. Attempts lightning-fast single-pass stream copy segmenting.
    2. If keyframes are sparse (e.g. short clips), uses parallel keyframe extraction.
    3. Guarantees MIN_SHARDS fragmentation in milliseconds.
    """
    os.makedirs(SHARD_FOLDER, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    num_shards = calculate_shards(file_path)

    start = time.perf_counter()
    total_duration = get_video_duration(file_path)
    shard_duration = max(1, math.ceil(total_duration / num_shards))

    seg_pattern = os.path.join(SHARD_FOLDER, f"{base_name}_part%03d.mp4")
    
    # Try ultra-fast single-pass segment muxer
    cmd = [
        "ffmpeg", "-y",
        "-i", file_path,
        "-c", "copy",
        "-f", "segment",
        "-segment_time", str(shard_duration),
        "-reset_timestamps", "1",
        "-movflags", "+faststart",
        seg_pattern
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=10)
    except Exception:
        pass

    created = [f for f in os.listdir(SHARD_FOLDER) if f.startswith(base_name) and f.endswith(".mp4")]

    # If keyframes prevented enough segments, fall back to parallel sub-seeking
    if len(created) < num_shards:
        for f in created:
            p = os.path.join(SHARD_FOLDER, f)
            if os.path.exists(p):
                os.remove(p)

        tasks = []
        actual_dur = total_duration / num_shards
        for i in range(num_shards):
            ss = i * actual_dur
            dur = actual_dur
            out = os.path.join(SHARD_FOLDER, f"{base_name}_part{i:03d}.mp4")
            tasks.append((i, ss, dur, out))

        workers = min(len(tasks), os.cpu_count() or 8)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_extract_shard, file_path, idx, ss, dur, out) for idx, ss, dur, out in tasks]
            for f in as_completed(futures):
                f.result()

    final_shards = [f for f in os.listdir(SHARD_FOLDER) if f.startswith(base_name) and f.endswith(".mp4")]
    elapsed = time.perf_counter() - start
    print(f"✔ Created {len(final_shards)} shards in {elapsed:.3f}s (High-Throughput Parallel)")
    return len(final_shards)


def _process_single(video_path):
    """Process one video: shard then delete original."""
    shard_video(video_path)
    os.remove(video_path)
    print(f"🗑 Deleted original video: {os.path.basename(video_path)}")


def process_uploads():
    if not os.path.exists(UPLOAD_FOLDER):
        print(f"⚠ No uploads folder found: {UPLOAD_FOLDER}")
        return

    videos = [f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith(('.mp4', '.mkv'))]
    if not videos:
        print("⚠ No videos found in uploads folder")
        return

    paths = [os.path.join(UPLOAD_FOLDER, v) for v in videos]

    if len(paths) == 1:
        _process_single(paths[0])
    else:
        # Process multiple videos in parallel
        workers = min(len(paths), os.cpu_count() or 4)
        print(f"▶ Processing {len(paths)} videos with {workers} workers")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_process_single, p): p for p in paths}
            for future in as_completed(futures):
                future.result()  # propagate exceptions

    print("🏁 All videos processed")


if __name__ == "__main__":
    process_uploads()
