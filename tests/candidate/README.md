# Candidate smoke checks

[简体中文](../../docs/zh-CN/tests/candidate/README.md)

[Test groups](../../docs/dev/testing.md) · [Corpus tools](../../docs/dev/corpus.md#verification-and-historical-records)

The focused candidate cases cover general/rating and frequency filtering, PMI and support thresholds, bounded continuous changes, and offline import. They use temporary SQLite databases and neutral tags; integration uses a simulated image service rather than real GPU work.

From the repository root, run the relevant file:

```shell
python -m unittest discover -s tests/candidate -p test_cooccurrence.py -v
python -m unittest discover -s tests -p test_cooccurrence_integration.py -v
```

Offline processing checks need the [corpus environment](../../docs/dev/corpus.md#files-and-preparation). Keep browser and full-dataset verification material under `dev/verification/`, and distinguish simulated results from real image-generation evidence.
