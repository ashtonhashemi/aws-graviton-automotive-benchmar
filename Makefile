.PHONY: test package

test:
	python3 tests/test_esc.py
	python3 benchmark/benchmark.py --records 10000 --iterations 2 --mode baseline --esc on --output /tmp/graviton-baseline.json
	python3 benchmark/benchmark.py --records 10000 --iterations 2 --mode optimized --esc on --output /tmp/graviton-optimized.json
	bash tests/test_udp_integration.sh
	python3 diagnostic_timing/p2_latency_sim.py --profile nominal --samples 5000 --output /tmp/p2-nominal.json
	python3 diagnostic_timing/p2_latency_sim.py --profile near_limit --samples 5000 --output /tmp/p2-near-limit.json
	python3 tests/test_p2_service.py

package:
	zip -r aws-graviton-automotive-benchmark.zip . -x '.git/*' '.aws-sam/*'
