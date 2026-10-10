from prometheus_client import Counter

events_consumed_total = Counter(
    "events_consumed_total", "Events consumed from RabbitMQ", ["event_type", "result"]
)
notifications_created_total = Counter(
    "notifications_created_total", "Notifications created", ["type"]
)
