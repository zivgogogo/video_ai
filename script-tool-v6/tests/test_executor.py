from app.pipeline.executor import compute_input_hash

def test_compute_input_hash_deterministic():
    h1 = compute_input_hash(text="hello", stage=1)
    h2 = compute_input_hash(text="hello", stage=1)
    assert h1 == h2

def test_compute_input_hash_different():
    h1 = compute_input_hash(text="hello", stage=1)
    h2 = compute_input_hash(text="world", stage=1)
    assert h1 != h2
