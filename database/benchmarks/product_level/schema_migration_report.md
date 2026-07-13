# Product Benchmark Schema Migration Report

- Canonical columns: 46
- Folders scanned: 4
- Files migrated: 11
- Files excluded: 7
- Incompatible files detected: 8

## Folders Scanned
- database/benchmarks/product_level/sample_1_morning
- database/benchmarks/product_level/sample_99_component_debug
- database/benchmarks/product_level/sample_101_apple_component_coverage
- database/benchmarks/product_level/sample_102_reference_debug

## Files Migrated
- database/benchmarks/product_level/sample_99_component_debug/apple_product_benchmark.csv
- database/benchmarks/product_level/sample_99_component_debug/master_results.csv
- database/benchmarks/product_level/sample_101_apple_component_coverage/apple_product_benchmark.csv
- database/benchmarks/product_level/sample_101_apple_component_coverage/master_results.csv
- database/benchmarks/product_level/sample_102_reference_debug/amd_product_benchmark.csv
- database/benchmarks/product_level/sample_102_reference_debug/apple_product_benchmark.csv
- database/benchmarks/product_level/sample_102_reference_debug/intel_product_benchmark.csv
- database/benchmarks/product_level/sample_102_reference_debug/master_results.csv
- database/benchmarks/product_level/sample_102_reference_debug/nvidia_product_benchmark.csv
- database/benchmarks/product_level/sample_102_reference_debug/samsung_product_benchmark.csv
- database/benchmarks/product_level/sample_102_reference_debug/tesla_product_benchmark.csv

## Files Excluded
- database/benchmarks/product_level/sample_1_morning/amd_product_benchmark.csv
- database/benchmarks/product_level/sample_1_morning/apple_product_benchmark.csv
- database/benchmarks/product_level/sample_1_morning/intel_product_benchmark.csv
- database/benchmarks/product_level/sample_1_morning/master_results.csv
- database/benchmarks/product_level/sample_1_morning/nvidia_product_benchmark.csv
- database/benchmarks/product_level/sample_1_morning/samsung_product_benchmark.csv
- database/benchmarks/product_level/sample_1_morning/tesla_product_benchmark.csv

## Missing Fields Filled
- database/benchmarks/product_level/sample_101_apple_component_coverage/apple_product_benchmark.csv: coverage_score, tier2_discovered_suppliers, tier2_verified_suppliers, tier2_verification_status, tier2_confidence, tier2_paths, tier3_discovered_suppliers, tier3_verified_suppliers, tier3_verification_status, tier3_confidence, tier3_paths
- database/benchmarks/product_level/sample_101_apple_component_coverage/master_results.csv: coverage_score, tier2_discovered_suppliers, tier2_verified_suppliers, tier2_verification_status, tier2_confidence, tier2_paths, tier3_discovered_suppliers, tier3_verified_suppliers, tier3_verification_status, tier3_confidence, tier3_paths
- database/benchmarks/product_level/sample_99_component_debug/apple_product_benchmark.csv: coverage_score, tier2_discovered_suppliers, tier2_verified_suppliers, tier2_verification_status, tier2_confidence, tier2_paths, tier3_discovered_suppliers, tier3_verified_suppliers, tier3_verification_status, tier3_confidence, tier3_paths
- database/benchmarks/product_level/sample_99_component_debug/master_results.csv: coverage_score, tier2_discovered_suppliers, tier2_verified_suppliers, tier2_verification_status, tier2_confidence, tier2_paths, tier3_discovered_suppliers, tier3_verified_suppliers, tier3_verification_status, tier3_confidence, tier3_paths

## Incompatible Files Detected
- database/benchmarks/product_level/sample_1_morning/amd_product_benchmark.csv: protected official sample was not modified
- database/benchmarks/product_level/sample_1_morning/apple_product_benchmark.csv: protected official sample was not modified
- database/benchmarks/product_level/sample_1_morning/intel_product_benchmark.csv: protected official sample was not modified
- database/benchmarks/product_level/sample_1_morning/master_results.csv: protected official sample was not modified
- database/benchmarks/product_level/sample_1_morning/nvidia_product_benchmark.csv: protected official sample was not modified
- database/benchmarks/product_level/sample_1_morning/samsung_product_benchmark.csv: protected official sample was not modified
- database/benchmarks/product_level/sample_1_morning/tesla_product_benchmark.csv: protected official sample was not modified
- database/benchmarks/product_level/sample_1_morning/master_results.csv: incompatible schema excluded from global master
