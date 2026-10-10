from prometheus_client import Counter

registrations_total = Counter("auth_registrations_total", "Successful user registrations")
logins_total = Counter("auth_logins_total", "Login attempts", ["result"])
events_published_total = Counter(
    "events_published_total", "Events published to RabbitMQ", ["event_type", "result"]
)
