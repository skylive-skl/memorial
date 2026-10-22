from config.celery import ping


def test_ping_task():
    assert ping.apply().get() == "pong"
