"""Write eval artifacts to the local LoopForge workspace."""

from __future__ import annotations

import json
from pathlib import Path

from loopforge.models.eval import EvalExample, EvaluatorDefinition, EvaluatorValidationRecord
from loopforge.paths import LOCAL_DIR


def write_eval_artifacts(
    root: Path,
    eval_example: EvalExample,
    evaluator: EvaluatorDefinition,
    validation: EvaluatorValidationRecord,
) -> dict[str, Path]:
    eval_dir = root / LOCAL_DIR / "evals"
    eval_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "eval": eval_dir / f"{eval_example.eval_id}.json",
        "evaluator": eval_dir / f"{evaluator.evaluator_id}.json",
        "validation": eval_dir / f"{evaluator.evaluator_id}-validation.json",
    }
    paths["eval"].write_text(
        json.dumps(eval_example.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["evaluator"].write_text(
        json.dumps(evaluator.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["validation"].write_text(
        json.dumps(validation.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return paths
