.PHONY: test package

test:
	python3 benchmark/benchmark.py --records 10000 --iterations 2 --mode baseline --output /tmp/graviton-baseline.json
	python3 benchmark/benchmark.py --records 10000 --iterations 2 --mode optimized --output /tmp/graviton-optimized.json

package:
	zip -r aws-graviton-automotive-benchmark.zip . -x '.git/*' '.aws-sam/*'
