from django.core.cache import cache

PROGRESS_TTL = 60 * 30  # 30 minutes


def set_progress(task_id, percent, message=""):
    cache.set(
        f"task_progress:{task_id}",
        {"percent": percent, "message": message},
        timeout=PROGRESS_TTL,
    )


def get_progress(task_id):
    return cache.get(
        f"task_progress:{task_id}",
        {"percent": 0, "message": "Pending"},
    )


def clear_progress(task_id):
    cache.delete(f"task_progress:{task_id}")
