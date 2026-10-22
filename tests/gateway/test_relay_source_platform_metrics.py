"""A removed metrics subscriber is not required to import gateway routing."""
def test_gateway_transport_does_not_load_builtin_metrics():
    from gateway.stream_consumer import GatewayStreamConsumer
    assert callable(GatewayStreamConsumer)
