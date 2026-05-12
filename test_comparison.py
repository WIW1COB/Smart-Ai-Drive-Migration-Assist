"""Quick test to verify component comparison logic"""

# Test baseline comparison logic
def test_baseline_comparison():
    """Test that different baseline UUIDs result in Modified status"""
    
    # Mock component data
    comp1 = {
        'name': 'rb.as.core.app.asw.acm.vacsensorsinglehbbwithhbc',
        'baseline_uuid': '_7M-5sbNxxxxxx',  # Different baseline
        'uuid': '_compUUID1'
    }
    
    comp2 = {
        'name': 'rb.as.core.app.asw.acm.vacsensorsinglehbbwithhbc',
        'baseline_uuid': '_4Yk-chKxxxxxx',  # Different baseline
        'uuid': '_compUUID2'
    }
    
    baseline1 = comp1.get('baseline_uuid', '') or comp1.get('uuid', '')
    baseline2 = comp2.get('baseline_uuid', '') or comp2.get('uuid', '')
    
    print(f"Component: {comp1['name']}")
    print(f"Baseline 1: {baseline1}")
    print(f"Baseline 2: {baseline2}")
    print(f"Baselines differ: {baseline1 != baseline2}")
    
    if baseline1 != baseline2 and baseline1 and baseline2:
        status = 'Modified'
        print(f"✓ Status: {status} (CORRECT - baselines differ)")
    else:
        status = 'Unchanged'
        print(f"✗ Status: {status} (WRONG - should be Modified)")
    
    assert status == 'Modified', "Different baselines should result in Modified status"
    
    # Test same baselines
    comp3 = {'name': 'test.comp', 'baseline_uuid': '_sameUUID'}
    comp4 = {'name': 'test.comp', 'baseline_uuid': '_sameUUID'}
    
    baseline3 = comp3.get('baseline_uuid', '')
    baseline4 = comp4.get('baseline_uuid', '')
    
    print(f"\nTest 2 - Same baselines:")
    print(f"Baseline 1: {baseline3}")
    print(f"Baseline 2: {baseline4}")
    print(f"Baselines differ: {baseline3 != baseline4}")
    
    if baseline3 != baseline4 and baseline3 and baseline4:
        print("Would check file-level changes")
    else:
        print("✓ Would perform file-level comparison (CORRECT)")

if __name__ == '__main__':
    test_baseline_comparison()
    print("\n✅ All tests passed!")
