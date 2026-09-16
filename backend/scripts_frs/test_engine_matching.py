import sys, os
sys.path.insert(0, os.path.abspath("."))
import time
import numpy as np
from app.frs_engine.frs_service import get_shared_engine

print("Testing get_shared_engine()...")
t0 = time.perf_counter()
face_model, matcher = get_shared_engine()
load_time = (time.perf_counter() - t0) * 1000

print(f"get_shared_engine() completed in {load_time:.2f} ms")
print(f"Matcher threshold: {matcher.threshold}")
print(f"Matcher gallery size: {matcher.gallery_size}")
print(f"Matcher identity count: {matcher.identity_count}")
print(f"FAISS index loaded: {matcher._faiss_index is not None}")
if matcher._faiss_index:
    print(f"FAISS total vectors: {matcher._faiss_index.ntotal}")

# Test matching with a vector from gallery
matrix, pids, names = matcher.gallery.get_flat_matrix()
if matrix.shape[0] > 0:
    test_emb = matrix[0]
    expected_pid = pids[0]
    expected_name = names[0]
    
    t_match = time.perf_counter()
    res = matcher.find_best_match(test_emb)
    match_latency_ms = (time.perf_counter() - t_match) * 1000
    
    print(f"\n--- MATCH TEST ---")
    print(f"Query test for: {expected_name} (ID: {expected_pid})")
    print(f"Match Result  : Name={res.name}, PID={res.person_id}, Similarity={res.similarity:.4f}, Known={res.is_known}")
    print(f"Match Latency : {match_latency_ms:.3f} ms")
    assert res.is_known, "Expected match to be known"
    assert res.similarity > 0.99, "Self similarity should be close to 1.0"
    print("\nSUCCESS: All FAISS matcher components verified and working perfectly!")
