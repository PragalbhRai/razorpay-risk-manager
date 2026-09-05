from app.streaming import worker


class FakeRedis:
    def __init__(self):
        self.set_calls = []
        self.xadd_calls = []
        self.xack_calls = []
        self.delete_calls = []

    def set(self, key, value):
        self.set_calls.append((key, value))

    def xadd(self, stream, fields):
        self.xadd_calls.append((stream, fields))

    def xack(self, stream, group, message_id):
        self.xack_calls.append((stream, group, message_id))

    def delete(self, key):
        self.delete_calls.append(key)


def test_failed_message_retries_then_moves_to_dlq(monkeypatch):
    redis_client = FakeRedis()
    attempts = []
    message_id = "123-0"
    data = {
        "transaction_id": "tx-1",
        "merchant_id": "merchant-1",
    }

    def fail_processing(transaction_id, message_data):
        attempts.append((transaction_id, message_data))
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(worker, "redis_client", redis_client)
    monkeypatch.setattr(worker, "process_transaction", fail_processing)

    result = worker.process_stream_message(message_id, data)

    retry_key = f"{worker.STREAM_NAME}:retries:{message_id}"
    assert result is False
    assert len(attempts) == worker.MAX_RETRY_ATTEMPTS
    assert redis_client.set_calls == [
        (retry_key, 1),
        (retry_key, 2),
        (retry_key, 3),
    ]
    assert len(redis_client.xadd_calls) == 1
    dlq_stream, dlq_fields = redis_client.xadd_calls[0]
    assert dlq_stream == worker.DLQ_STREAM_NAME
    assert dlq_fields["transaction_id"] == "tx-1"
    assert dlq_fields["original_message_id"] == message_id
    assert dlq_fields["retry_attempts"] == str(worker.MAX_RETRY_ATTEMPTS)
    assert dlq_fields["error"] == "database unavailable"
    assert redis_client.xack_calls == [
        (worker.STREAM_NAME, worker.CONSUMER_GROUP, message_id),
    ]
    assert redis_client.delete_calls == [retry_key]