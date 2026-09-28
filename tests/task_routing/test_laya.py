import json
import time
from pathlib import Path

import laya


MODEL_PATH = "/home/prince/projects/speed/models/laya"
BENCHMARK_PATH = Path("tests/task_routing/benchmark.json")


QUESTIONS = {
    "task": {
        "type": "choice",
        "instructions": "What is the primary task type?",
        "criteria": {
            "coding": (
                "Writing, debugging, explaining, or modifying "
                "computer code."
            ),
            "reasoning": (
                "Complex logical, mathematical, analytical, "
                "or multi-step reasoning."
            ),
            "general": (
                "General conversation, explanation, knowledge "
                "questions, or tasks that do not fit the other categories."
            ),
        },
    }
}


def load_benchmarks() -> list[dict]:
    with BENCHMARK_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def test_laya_task_routing():
    benchmarks = load_benchmarks()

    print(f"\nLoaded {len(benchmarks)} benchmark prompts")

    print("Loading Laya...")
    load_start = time.perf_counter()

    model = laya.load(
        MODEL_PATH,
        device="cuda",
    )

    load_time = time.perf_counter() - load_start

    print(f"Laya loaded in {load_time:.2f}s\n")

    correct = 0
    latencies = []

    confusion = {
        "coding": {
            "coding": 0,
            "reasoning": 0,
            "general": 0,
        },
        "reasoning": {
            "coding": 0,
            "reasoning": 0,
            "general": 0,
        },
        "general": {
            "coding": 0,
            "reasoning": 0,
            "general": 0,
        },
    }

    print("Running benchmark...\n")

    for index, benchmark in enumerate(benchmarks, start=1):
        prompt = benchmark["text"]
        expected = benchmark["expected"]

        start = time.perf_counter()

        result = model.predict(
            prompt,
            QUESTIONS,
        )

        elapsed = (
            time.perf_counter() - start
        ) * 1000

        answer = result["answers"]["task"]

        predicted = answer["choice"]

        latencies.append(elapsed)

        confusion[expected][predicted] += 1

        if predicted == expected:
            correct += 1
            status = "PASS"
        else:
            status = "FAIL"

        print(
            f"[{index:02d}/{len(benchmarks)}] "
            f"{status} | "
            f"expected={expected:<9} "
            f"predicted={predicted:<9} "
            f"{elapsed:>8.2f} ms"
        )

    total = len(benchmarks)
    accuracy = correct / total * 100

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    print(f"Total:     {total}")
    print(f"Correct:   {correct}")
    print(f"Incorrect: {total - correct}")
    print(f"Accuracy:  {accuracy:.2f}%")

    print("\nLatency:")
    print(f"  Min:     {min(latencies):.2f} ms")
    print(f"  Max:     {max(latencies):.2f} ms")
    print(f"  Average: {sum(latencies) / total:.2f} ms")

    if len(latencies) > 1:
        warm_latencies = latencies[1:]

        print(
            f"  Warm:    "
            f"{sum(warm_latencies) / len(warm_latencies):.2f} ms"
        )

    print("\nConfusion Matrix:")
    print(
        f"{'Expected':<12}"
        f"{'Coding':>10}"
        f"{'Reasoning':>12}"
        f"{'General':>10}"
    )

    for expected in ["coding", "reasoning", "general"]:
        print(
            f"{expected:<12}"
            f"{confusion[expected]['coding']:>10}"
            f"{confusion[expected]['reasoning']:>12}"
            f"{confusion[expected]['general']:>10}"
        )

    print("=" * 70)

    assert accuracy >= 0