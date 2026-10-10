from prometheus_client import Counter

events_published_total = Counter(
    "events_published_total", "Events published to RabbitMQ", ["event_type", "result"]
)
tasks_created_total = Counter("tasks_created_total", "Tasks created")
task_status_changes_total = Counter(
    "task_status_changes_total", "Task status changes", ["from_status", "to_status"]
)
events_consumed_total = Counter(
    "events_consumed_total", "Events consumed from RabbitMQ", ["event_type", "result"]
)
cache_requests_total = Counter("cache_requests_total", "Cache lookups", ["result"])
