from backend.services.data_fusion import fuse_sources

def test_fusion_clamps_congestion():
    result = fuse_sources({"congestion_index": 5, "speed_kmph": 80})
    assert result["congestion_index"] == 1.0
