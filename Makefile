.PHONY: test package

test:
	python3 tests/test_esc.py
	python3 benchmark/benchmark.py --records 10000 --iterations 2 --mode baseline --esc on --output /tmp/graviton-baseline.json
	python3 benchmark/benchmark.py --records 10000 --iterations 2 --mode optimized --esc on --output /tmp/graviton-optimized.json

package:
	zip -r aws-graviton-automotive-benchmark.zip . -x '.git/*' '.aws-sam/*'
