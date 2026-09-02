from datetime import datetime, timezone

def is_within_playback_window(window):
    start = datetime.fromisoformat(window["start"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(window["end"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)

    return start <= now <= end
