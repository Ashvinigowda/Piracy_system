"""
CinemaShield — AI/ML Security Intelligence Engine
───────────────────────────────────────────────────
Provides video content analysis, anomaly detection,
threat scoring, and forensic fingerprinting without
requiring heavy ML libraries (uses stdlib + ffprobe).
"""

import os
import json
import math
import hashlib
import subprocess
import statistics
from datetime import datetime, timezone, timedelta
from collections import defaultdict


# ═══════════════════════════════════════════
# 1. VIDEO CONTENT ANALYSIS (ffprobe-based)
# ═══════════════════════════════════════════

def analyze_video(file_path):
    """
    Extract detailed metadata from a video file using ffprobe.
    Returns a rich analysis dict with quality metrics.
    """
    if not os.path.exists(file_path):
        return {'error': 'File not found'}

    # Get full probe JSON
    cmd = [
        'ffprobe', '-v', 'quiet',
        '-print_format', 'json',
        '-show_format', '-show_streams',
        file_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        probe = json.loads(result.stdout)
    except Exception as e:
        return {'error': f'FFprobe failed: {str(e)}'}

    fmt = probe.get('format', {})
    streams = probe.get('streams', [])

    video_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
    audio_stream = next((s for s in streams if s.get('codec_type') == 'audio'), None)

    file_size = int(fmt.get('size', 0))
    duration = float(fmt.get('duration', 0))
    bitrate = int(fmt.get('bit_rate', 0))

    analysis = {
        'filename': os.path.basename(file_path),
        'format': fmt.get('format_long_name', 'Unknown'),
        'duration_sec': round(duration, 2),
        'duration_human': _human_duration(duration),
        'file_size_bytes': file_size,
        'file_size_human': _human_size(file_size),
        'bitrate_kbps': round(bitrate / 1000) if bitrate else 0,
        'streams_count': len(streams),
    }

    # Video analysis
    if video_stream:
        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        fps_parts = video_stream.get('r_frame_rate', '0/1').split('/')
        fps = round(int(fps_parts[0]) / max(int(fps_parts[1]), 1), 2) if len(fps_parts) == 2 else 0

        analysis['video'] = {
            'codec': video_stream.get('codec_name', 'Unknown'),
            'profile': video_stream.get('profile', 'Unknown'),
            'width': width,
            'height': height,
            'resolution': f'{width}x{height}',
            'resolution_class': _classify_resolution(width, height),
            'fps': fps,
            'pixel_format': video_stream.get('pix_fmt', 'Unknown'),
        }

        # Quality score (0-100)
        analysis['quality_score'] = _compute_quality_score(width, height, fps, bitrate, duration)

    # Audio analysis
    if audio_stream:
        analysis['audio'] = {
            'codec': audio_stream.get('codec_name', 'Unknown'),
            'sample_rate': int(audio_stream.get('sample_rate', 0)),
            'channels': int(audio_stream.get('channels', 0)),
            'channel_layout': audio_stream.get('channel_layout', 'Unknown'),
        }

    # Content tags (AI-style classification based on metadata heuristics)
    analysis['content_tags'] = _generate_content_tags(analysis)

    return analysis


def _classify_resolution(w, h):
    pixels = w * h
    if pixels >= 3840 * 2160:
        return '4K Ultra HD'
    elif pixels >= 1920 * 1080:
        return 'Full HD (1080p)'
    elif pixels >= 1280 * 720:
        return 'HD (720p)'
    elif pixels >= 854 * 480:
        return 'SD (480p)'
    else:
        return 'Low Resolution'


def _compute_quality_score(w, h, fps, bitrate, duration):
    """Score 0-100 based on resolution, FPS, bitrate efficiency."""
    score = 0

    # Resolution (max 40 pts)
    pixels = w * h
    if pixels >= 3840 * 2160:
        score += 40
    elif pixels >= 1920 * 1080:
        score += 32
    elif pixels >= 1280 * 720:
        score += 22
    elif pixels >= 854 * 480:
        score += 14
    else:
        score += 6

    # FPS (max 20 pts)
    if fps >= 60:
        score += 20
    elif fps >= 30:
        score += 15
    elif fps >= 24:
        score += 12
    else:
        score += 5

    # Bitrate efficiency (max 25 pts)
    if bitrate > 0 and pixels > 0:
        bpp = bitrate / (pixels * max(fps, 1))  # bits per pixel per frame
        if bpp > 0.1:
            score += 25
        elif bpp > 0.05:
            score += 18
        elif bpp > 0.02:
            score += 12
        else:
            score += 5

    # Duration sanity bonus (max 15 pts) — feature-length movies score higher
    if duration >= 5400:      # 90+ min
        score += 15
    elif duration >= 3600:    # 60+ min
        score += 12
    elif duration >= 600:     # 10+ min
        score += 8
    elif duration >= 60:
        score += 4
    else:
        score += 1

    return min(score, 100)


def _generate_content_tags(analysis):
    """Generate descriptive tags based on video metadata (ML-style heuristic)."""
    tags = []

    v = analysis.get('video', {})
    if v:
        tags.append(v.get('resolution_class', ''))
        if v.get('fps', 0) >= 60:
            tags.append('High Frame Rate')
        if v.get('codec') == 'hevc' or v.get('codec') == 'h265':
            tags.append('HEVC Encoded')
        elif v.get('codec') == 'h264':
            tags.append('H.264 Encoded')
        if v.get('profile') == 'High 10':
            tags.append('10-bit Color')

    a = analysis.get('audio', {})
    if a:
        if a.get('channels', 0) >= 6:
            tags.append('Surround Sound')
        elif a.get('channels', 0) >= 2:
            tags.append('Stereo Audio')
        if a.get('sample_rate', 0) >= 48000:
            tags.append('Hi-Fi Audio')

    dur = analysis.get('duration_sec', 0)
    if dur >= 5400:
        tags.append('Feature Length')
    elif dur >= 1200:
        tags.append('Short Film')
    elif dur >= 60:
        tags.append('Clip')

    score = analysis.get('quality_score', 0)
    if score >= 80:
        tags.append('Premium Quality')
    elif score >= 60:
        tags.append('Good Quality')
    elif score >= 40:
        tags.append('Standard Quality')

    return [t for t in tags if t]


def _human_duration(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    if h > 0:
        return f'{h}h {m}m {s}s'
    elif m > 0:
        return f'{m}m {s}s'
    return f'{s}s'


def _human_size(b):
    if b < 1024:
        return f'{b} B'
    elif b < 1048576:
        return f'{b / 1024:.1f} KB'
    elif b < 1073741824:
        return f'{b / 1048576:.1f} MB'
    return f'{b / 1073741824:.2f} GB'


# ═══════════════════════════════════════════
# 2. ANOMALY DETECTION (audit log analysis)
# ═══════════════════════════════════════════

def detect_anomalies(audit_log_path):
    """
    Analyze audit log for suspicious patterns:
    - Rapid repeated auth failures (brute-force)
    - Unusual access times
    - Multiple IPs for same action burst
    - Session expiry anomalies
    """
    if not os.path.exists(audit_log_path):
        return {'anomalies': [], 'risk_level': 'low', 'score': 0}

    with open(audit_log_path, 'r') as f:
        try:
            log = json.load(f)
        except json.JSONDecodeError:
            return {'anomalies': [], 'risk_level': 'low', 'score': 0}

    anomalies = []
    risk_score = 0

    # Group events by type and time
    failures = [e for e in log if 'FAIL' in e.get('action', '')]
    auths = [e for e in log if 'AUTH' in e.get('action', '')]
    all_ips = [e.get('ip') for e in log if e.get('ip')]

    # (A) Brute-force detection: >3 failures in 5 minutes
    failure_times = _parse_timestamps(failures)
    burst_count = _count_bursts(failure_times, window_sec=300)
    if burst_count > 0:
        anomalies.append({
            'type': 'BRUTE_FORCE',
            'severity': 'high',
            'message': f'Detected {burst_count} burst(s) of auth failures (>3 in 5 min)',
            'recommendation': 'Consider implementing rate limiting or IP blocking'
        })
        risk_score += 35

    # (B) Unusual hours: actions between 1 AM - 5 AM UTC
    late_night = [e for e in log if _is_late_night(e.get('timestamp', ''))]
    if len(late_night) > 2:
        anomalies.append({
            'type': 'UNUSUAL_HOURS',
            'severity': 'medium',
            'message': f'{len(late_night)} actions detected during unusual hours (01:00-05:00 UTC)',
            'recommendation': 'Verify if these are legitimate theatre operations'
        })
        risk_score += 15

    # (C) Multiple unique IPs
    unique_ips = set(all_ips)
    if len(unique_ips) > 5:
        anomalies.append({
            'type': 'MULTI_IP',
            'severity': 'medium',
            'message': f'{len(unique_ips)} unique IP addresses detected in audit log',
            'recommendation': 'Ensure only authorised devices access the system'
        })
        risk_score += 10

    # (D) Excessive failed attempts total
    if len(failures) > 10:
        anomalies.append({
            'type': 'HIGH_FAILURE_RATE',
            'severity': 'high',
            'message': f'{len(failures)} total failed attempts recorded',
            'recommendation': 'Investigate potential unauthorized access attempts'
        })
        risk_score += 25

    # (E) Shard tampering: integrity failures
    tampering = [e for e in log if 'integrity' in json.dumps(e.get('details', {})).lower()]
    if tampering:
        anomalies.append({
            'type': 'SHARD_TAMPERING',
            'severity': 'critical',
            'message': f'{len(tampering)} integrity check failure(s) detected',
            'recommendation': 'Re-encrypt and re-distribute shards immediately'
        })
        risk_score += 50

    # Classify
    risk_score = min(risk_score, 100)
    if risk_score >= 60:
        risk_level = 'critical'
    elif risk_score >= 35:
        risk_level = 'high'
    elif risk_score >= 15:
        risk_level = 'medium'
    else:
        risk_level = 'low'

    return {
        'anomalies': anomalies,
        'risk_level': risk_level,
        'risk_score': risk_score,
        'total_events': len(log),
        'failure_count': len(failures),
        'unique_ips': len(unique_ips),
        'analyzed_at': datetime.now(timezone.utc).isoformat()
    }


def _parse_timestamps(entries):
    times = []
    for e in entries:
        ts = e.get('timestamp', '')
        try:
            ts = ts.rstrip('Z')
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            times.append(dt)
        except (ValueError, TypeError):
            pass
    return sorted(times)


def _count_bursts(times, window_sec=300):
    """Count how many bursts of >=3 events exist within a sliding window."""
    if len(times) < 3:
        return 0
    bursts = 0
    i = 0
    while i < len(times):
        window_end = times[i] + timedelta(seconds=window_sec)
        count = sum(1 for t in times[i:] if t <= window_end)
        if count >= 3:
            bursts += 1
            # Skip past this burst
            i += count
        else:
            i += 1
    return bursts


def _is_late_night(ts_str):
    try:
        ts = ts_str.rstrip('Z')
        dt = datetime.fromisoformat(ts)
        return 1 <= dt.hour <= 5
    except (ValueError, TypeError, AttributeError):
        return False


# ═══════════════════════════════════════════
# 3. RISK SCORING (per-session assessment)
# ═══════════════════════════════════════════

def compute_session_risk(theatre_id, ip_address, audit_log_path):
    """
    Calculate a risk score (0-100) for a specific playback session
    based on historical behaviour and current context.
    """
    risk = 0
    factors = []

    if not os.path.exists(audit_log_path):
        return {'score': 0, 'level': 'low', 'factors': []}

    with open(audit_log_path, 'r') as f:
        try:
            log = json.load(f)
        except json.JSONDecodeError:
            return {'score': 0, 'level': 'low', 'factors': []}

    # Factor 1: Recent failure ratio for this IP
    recent = [e for e in log[-50:] if e.get('ip') == ip_address]
    recent_fails = [e for e in recent if 'FAIL' in e.get('action', '')]
    if len(recent) > 0:
        fail_ratio = len(recent_fails) / len(recent)
        if fail_ratio > 0.5:
            risk += 30
            factors.append(f'High failure ratio ({len(recent_fails)}/{len(recent)} recent attempts)')
        elif fail_ratio > 0.2:
            risk += 15
            factors.append(f'Elevated failure ratio ({len(recent_fails)}/{len(recent)} recent attempts)')

    # Factor 2: First-time IP
    all_ips = {e.get('ip') for e in log}
    if ip_address not in all_ips:
        risk += 10
        factors.append('First-time IP address')

    # Factor 3: Theatre ID mismatch (accessing a theatre not seen before)
    theatre_events = [e for e in log if e.get('details', {}).get('theatre_id') == theatre_id]
    if not theatre_events:
        risk += 15
        factors.append(f'Theatre "{theatre_id}" has no prior history')

    # Factor 4: Access velocity (many requests in last minute)
    now = datetime.now(timezone.utc)
    recent_1min = [e for e in log if _within_seconds(e.get('timestamp', ''), now, 60)]
    if len(recent_1min) > 10:
        risk += 20
        factors.append(f'{len(recent_1min)} requests in last minute (high velocity)')

    # Factor 5: Late-night access
    if 1 <= now.hour <= 5:
        risk += 10
        factors.append('Access during unusual hours (01:00-05:00 UTC)')

    risk = min(risk, 100)
    level = 'critical' if risk >= 60 else 'high' if risk >= 35 else 'medium' if risk >= 15 else 'low'

    return {'score': risk, 'level': level, 'factors': factors}


def _within_seconds(ts_str, now, seconds):
    try:
        ts = ts_str.rstrip('Z')
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).total_seconds() < seconds
    except (ValueError, TypeError, AttributeError):
        return False


# ═══════════════════════════════════════════
# 4. FORENSIC FINGERPRINTING
# ═══════════════════════════════════════════

def generate_forensic_fingerprint(theatre_id, session_token, ip_address, timestamp=None):
    """
    Generate a unique forensic fingerprint for a playback session.
    This can be embedded as invisible watermark data for leak tracing.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    payload = f'{theatre_id}|{session_token}|{ip_address}|{timestamp}'
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()

    return {
        'fingerprint': fingerprint,
        'fingerprint_short': fingerprint[:16],
        'theatre_id': theatre_id,
        'session_token': session_token[:8] + '...',
        'generated_at': timestamp,
        'payload_hash': hashlib.md5(payload.encode()).hexdigest()[:12],
        'traceable': True
    }


# ═══════════════════════════════════════════
# 5. ANALYTICS SUMMARY
# ═══════════════════════════════════════════

def generate_analytics_summary(audit_log_path):
    """
    Produce a comprehensive analytics summary from the audit log:
    - Event counts by type
    - Timeline data for charts
    - Uptime / success rates
    """
    if not os.path.exists(audit_log_path):
        return _empty_summary()

    with open(audit_log_path, 'r') as f:
        try:
            log = json.load(f)
        except json.JSONDecodeError:
            return _empty_summary()

    if not log:
        return _empty_summary()

    # Event counts
    action_counts = defaultdict(int)
    for e in log:
        action_counts[e.get('action', 'UNKNOWN')] += 1

    # Hourly distribution
    hourly = defaultdict(int)
    for e in log:
        try:
            ts = e.get('timestamp', '').rstrip('Z')
            dt = datetime.fromisoformat(ts)
            hourly[dt.hour] += 1
        except (ValueError, TypeError):
            pass

    # Success vs failure
    total_auths = sum(1 for e in log if 'AUTH' in e.get('action', ''))
    failed_auths = sum(1 for e in log if 'FAIL' in e.get('action', ''))
    success_auths = total_auths - failed_auths

    # Unique IPs
    unique_ips = list(set(e.get('ip') for e in log if e.get('ip')))

    # Recent activity (last 24h)
    now = datetime.now(timezone.utc)
    recent_24h = sum(1 for e in log if _within_seconds(e.get('timestamp', ''), now, 86400))

    return {
        'total_events': len(log),
        'recent_24h': recent_24h,
        'action_counts': dict(action_counts),
        'hourly_distribution': {str(h): hourly.get(h, 0) for h in range(24)},
        'auth_stats': {
            'total': total_auths,
            'success': success_auths,
            'failed': failed_auths,
            'success_rate': round(success_auths / max(total_auths, 1) * 100, 1)
        },
        'unique_ips': unique_ips,
        'unique_ip_count': len(unique_ips),
        'generated_at': now.isoformat()
    }


def _empty_summary():
    return {
        'total_events': 0,
        'recent_24h': 0,
        'action_counts': {},
        'hourly_distribution': {str(h): 0 for h in range(24)},
        'auth_stats': {'total': 0, 'success': 0, 'failed': 0, 'success_rate': 100.0},
        'unique_ips': [],
        'unique_ip_count': 0,
        'generated_at': datetime.now(timezone.utc).isoformat()
    }
