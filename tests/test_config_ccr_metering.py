from coderouter_plugin_compress.ccr import CCRStore
from coderouter_plugin_compress.config import CompressConfig
from coderouter_plugin_compress.metering import count_tokens, heuristic_tokens


def test_config_defaults_and_validation():
    c = CompressConfig.from_kwargs()
    assert c.mode == "safe"
    assert c.min_block_tokens == 200
    # Invalid values fall back instead of raising.
    bad = CompressConfig.from_kwargs(mode="nonsense", min_block_tokens="x", crushers=["bogus"])
    assert bad.mode == "safe"
    assert bad.min_block_tokens == 200
    assert bad.crushers == ("json", "log", "text")


def test_config_nested_metering_path():
    c = CompressConfig.from_kwargs(metering={"tokenizer_path": "/tmp/tok.json"})
    assert c.metering_tokenizer_path == "/tmp/tok.json"
    c2 = CompressConfig.from_kwargs(metering_tokenizer_path="/tmp/flat.json")
    assert c2.metering_tokenizer_path == "/tmp/flat.json"


def test_ccr_store_roundtrip_and_idempotent():
    store = CCRStore(max_entries=4)
    k1 = store.put("hello world")
    k2 = store.put("hello world")
    assert k1 == k2  # same content → same id
    assert store.get(k1) == "hello world"
    assert len(store) == 1


def test_ccr_lru_eviction():
    store = CCRStore(max_entries=2)
    a = store.put("a" * 50)
    b = store.put("b" * 50)
    store.put("c" * 50)  # evicts oldest (a)
    assert store.get(a) is None
    assert store.get(b) is not None
    assert len(store) == 2


def test_metering_heuristic_and_fallback():
    assert heuristic_tokens("") == 0
    assert heuristic_tokens("abcd") == 1
    # Missing tokenizer path → heuristic fallback, still an int.
    assert count_tokens("abcdefgh", "/nonexistent/tok.json") == 2
